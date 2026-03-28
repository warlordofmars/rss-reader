from pathlib import Path

from aws_cdk import (  # noqa: I001
    BundlingOptions,
    CfnOutput,
    DockerImage,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_certificatemanager as acm,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_route53 as route53,
    aws_route53_targets as r53_targets,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

HOSTED_ZONE_ID = "Z3E3AQ9RR5XH0V"
CERTIFICATE_ID = "471106fc-e3dd-4e0b-a20f-010a6e326283"
GITHUB_REPO = "warlordofmars/rss-reader"  # org/repo for OIDC trust policy


class RssReaderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── DynamoDB single table ──────────────────────────────────────────────
        #
        # Item shapes:
        #   User    PK=USER#<google_id>   SK=#META
        #   Feed    PK=USER#<google_id>   SK=FEED#<feed_id>
        #   Article PK=FEED#<feed_id>     SK=ARTICLE#<published_at_iso>#<guid_hash>
        #   Guid    PK=FEED#<feed_id>     SK=GUID#<guid_hash>   (dedup sentinel)
        #
        # GSI1 (sparse, Feed items only):
        #   GSI1PK=ALL_FEEDS  →  returns all feeds across all users (scheduler)
        #
        # GSI2 (Article items only):
        #   GSI2PK=USER#<google_id>  GSI2SK=<published_at_iso>#<guid_hash>
        #   →  user's articles sorted newest-first across all feeds
        #
        table = dynamodb.Table(
            self,
            "Table",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(name="GSI1PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="GSI1SK", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["feed_id", "user_id", "url", "title"],
        )

        table.add_global_secondary_index(
            index_name="GSI2",
            partition_key=dynamodb.Attribute(name="GSI2PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="GSI2SK", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=[
                "feed_id",
                "title",
                "link",
                "summary",
                "published_at",
                "is_read",
                "content_s3_key",
            ],
        )

        self.table = table

        # ── S3 bucket for article content overflow (> 300 KB) ─────────────────
        content_bucket = s3.Bucket(
            self,
            "ArticleContentBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=False,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.content_bucket = content_bucket

        # ── Secrets Manager ───────────────────────────────────────────────────
        # Stores sensitive app config. Populate after first deploy with:
        #   aws secretsmanager put-secret-value \
        #     --secret-id rss-reader/app \
        #     --secret-string '{
        #       "GOOGLE_CLIENT_ID": "...",
        #       "GOOGLE_CLIENT_SECRET": "...",
        #       "JWT_SECRET": "<random-string>"
        #     }'
        app_secret = secretsmanager.Secret(
            self,
            "AppSecret",
            description=(
                "RSS Reader secrets: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET. "
                "Populate manually after first deploy."
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Shared DNS / TLS resources ────────────────────────────────────────
        zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            "HostedZone",
            hosted_zone_id=HOSTED_ZONE_ID,
            zone_name="warlordofmars.net",
        )

        # Existing ACM certificate (us-east-1) — used for CloudFront (frontend)
        certificate = acm.Certificate.from_certificate_arn(
            self,
            "Certificate",
            f"arn:aws:acm:us-east-1:{self.account}:certificate/{CERTIFICATE_ID}",
        )

        # Separate certificate for the API custom domain — CDK provisions and
        # validates it via DNS using the existing hosted zone.
        api_certificate = acm.Certificate(
            self,
            "ApiCertificate",
            domain_name="api.rss.warlordofmars.net",
            validation=acm.CertificateValidation.from_dns(zone),
        )

        # ── Lambda function ───────────────────────────────────────────────────
        # Bundled via Docker: pip-installs production deps then copies source .py files.
        # Requires Docker to be running during `cdk deploy`.
        api_fn = lambda_.Function(
            self,
            "ApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                str(BACKEND_DIR),
                exclude=[
                    "tests",
                    ".venv",
                    "__pycache__",
                    "*.db",
                    ".env",
                    ".env.example",
                    "uv.lock",
                    "pyproject.toml",
                    "node_modules",
                ],
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_13.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        " && ".join([
                            "pip install --no-cache-dir"
                            " 'fastapi[standard]' feedparser apscheduler authlib boto3 mangum"
                            " httpx python-dotenv 'python-jose[cryptography]'"
                            " -t /asset-output",
                            "cp *.py /asset-output/",
                        ]),
                    ],
                ),
            ),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "DYNAMODB_TABLE": table.table_name,
                "CONTENT_BUCKET": content_bucket.bucket_name,
                "APP_SECRET_ARN": app_secret.secret_arn,
                "REDIRECT_URI": "https://api.rss.warlordofmars.net/auth/callback",
                "FRONTEND_URL": "https://rss.warlordofmars.net",
            },
        )

        # IAM: grant Lambda access to the resources it needs
        table.grant_read_write_data(api_fn)
        content_bucket.grant_read_write(api_fn)
        app_secret.grant_read(api_fn)

        self.api_fn = api_fn

        # ── API Gateway (REST API, proxy to Lambda) ────────────────────────────
        # All requests forwarded to FastAPI via Lambda proxy integration.
        # CORS is handled by FastAPI's CORSMiddleware — not configured here.
        rest_api = apigw.LambdaRestApi(
            self,
            "RestApi",
            handler=api_fn,
            proxy=True,
            deploy_options=apigw.StageOptions(stage_name="prod"),
            # Binary media types needed for any future binary responses
            binary_media_types=["*/*"],
        )

        self.rest_api = rest_api

        # ── API Gateway custom domain: api.rss.warlordofmars.net ──────────────
        # Edge-optimised domain — certificate must be in us-east-1 (same cert as
        # CloudFront).  Base path mapping "/" routes all traffic to the prod stage.
        api_domain = apigw.DomainName(
            self,
            "ApiDomainName",
            domain_name="api.rss.warlordofmars.net",
            certificate=api_certificate,
            endpoint_type=apigw.EndpointType.EDGE,
            mapping=rest_api,
        )

        route53.ARecord(
            self,
            "ApiARecord",
            zone=zone,
            record_name="api.rss",
            target=route53.RecordTarget.from_alias(
                r53_targets.ApiGatewayDomain(api_domain)
            ),
        )

        # ── EventBridge scheduler (every 30 min) ──────────────────────────────
        # Replaces APScheduler — Lambda is stateless so the scheduler cannot run
        # inside the process.  handler.py detects source=="aws.events" and calls
        # fetcher.fetch_all_feeds() instead of routing through Mangum.
        rule = events.Rule(
            self,
            "FeedRefreshRule",
            schedule=events.Schedule.rate(Duration.minutes(30)),
            description="Trigger RSS feed refresh every 30 minutes",
        )
        rule.add_target(targets.LambdaFunction(api_fn))

        # ── Frontend: S3 + CloudFront + Route53 ───────────────────────────────
        # Private S3 bucket — CloudFront serves content via OAC
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(frontend_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            domain_names=["rss.warlordofmars.net"],
            certificate=certificate,
            default_root_object="index.html",
            # SPA: return index.html for 403/404 so React Router handles routing
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        # DNS: rss.warlordofmars.net → CloudFront
        route53.ARecord(
            self,
            "FrontendARecord",
            zone=zone,
            record_name="rss",
            target=route53.RecordTarget.from_alias(
                r53_targets.CloudFrontTarget(distribution)
            ),
        )

        # Build frontend with Docker (node:20-alpine) and deploy to S3
        s3deploy.BucketDeployment(
            self,
            "FrontendDeployment",
            sources=[
                s3deploy.Source.asset(
                    str(FRONTEND_DIR),
                    exclude=["node_modules", ".venv", "dist"],
                    bundling=BundlingOptions(
                        image=DockerImage.from_registry("node:20-alpine"),
                        environment={"VITE_API_URL": "https://api.rss.warlordofmars.net"},
                        command=[
                            "sh",
                            "-c",
                            "npm ci --cache /tmp/npm-cache"
                            " && npm run build"
                            " && cp -r dist/* /asset-output/",
                        ],
                    ),
                )
            ],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # ── GitHub Actions OIDC deploy role ───────────────────────────────────
        # Allows GitHub Actions to assume this role without long-lived keys.
        # First deploy must be done manually (chicken-and-egg); after that CI
        # deploys automatically on every push to main.
        github_oidc = iam.OpenIdConnectProvider(
            self,
            "GitHubOidcProvider",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )

        deploy_role = iam.Role(
            self,
            "GitHubActionsDeployRole",
            assumed_by=iam.WebIdentityPrincipal(
                github_oidc.open_id_connect_provider_arn,
                conditions={
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": (
                            f"repo:{GITHUB_REPO}:*"
                        ),
                    },
                },
            ),
            # AdministratorAccess is appropriate here — CDK needs to create/update
            # any resource type in the stack.
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
            ],
            description="Assumed by GitHub Actions to deploy the RSS Reader CDK stack",
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "TableName", value=table.table_name, export_name="RssReaderTableName")
        CfnOutput(
            self,
            "ContentBucketName",
            value=content_bucket.bucket_name,
            export_name="RssReaderContentBucketName",
        )
        CfnOutput(
            self,
            "ContentBucketArn",
            value=content_bucket.bucket_arn,
            export_name="RssReaderContentBucketArn",
        )
        CfnOutput(
            self,
            "ApiUrl",
            value=rest_api.url,
            export_name="RssReaderApiUrl",
        )
        CfnOutput(
            self,
            "AppSecretArn",
            value=app_secret.secret_arn,
            description="Populate via ARN: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET",
            export_name="RssReaderAppSecretArn",
        )
        CfnOutput(
            self,
            "LambdaFunctionName",
            value=api_fn.function_name,
            export_name="RssReaderLambdaFunctionName",
        )
        CfnOutput(
            self,
            "FrontendBucketName",
            value=frontend_bucket.bucket_name,
            export_name="RssReaderFrontendBucketName",
        )
        CfnOutput(
            self,
            "FrontendDistributionId",
            value=distribution.distribution_id,
            export_name="RssReaderFrontendDistributionId",
        )
        CfnOutput(
            self,
            "FrontendUrl",
            value="https://rss.warlordofmars.net",
            export_name="RssReaderFrontendUrl",
        )
        CfnOutput(
            self,
            "ApiCustomDomain",
            value="https://api.rss.warlordofmars.net",
            export_name="RssReaderApiCustomDomain",
        )
        CfnOutput(
            self,
            "GitHubActionsDeployRoleArn",
            value=deploy_role.role_arn,
            description="Set as AWS_DEPLOY_ROLE_ARN in GitHub Actions secrets",
            export_name="RssReaderGitHubActionsDeployRoleArn",
        )
