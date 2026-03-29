import os
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
    aws_cloudwatch as cw,
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

# Injected at deploy time by CI (e.g. "1.2.3"); falls back to "dev" locally
APP_VERSION = os.environ.get("APP_VERSION", "dev")

HOSTED_ZONE_ID = "Z3E3AQ9RR5XH0V"
CERTIFICATE_ID = "471106fc-e3dd-4e0b-a20f-010a6e326283"
GITHUB_REPO = "warlordofmars/rss-reader"  # org/repo for OIDC trust policy

DOMAIN_BASE = "warlordofmars.net"


class RssReaderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, env_name: str = "prod", **kwargs) -> None:  # noqa: E501
        super().__init__(scope, construct_id, **kwargs)

        is_prod = env_name == "prod"
        if is_prod:
            frontend_domain = f"rss.{DOMAIN_BASE}"
            api_domain = f"api.rss.{DOMAIN_BASE}"
        else:
            frontend_domain = f"rss-{env_name}.{DOMAIN_BASE}"
            api_domain = f"api.rss-{env_name}.{DOMAIN_BASE}"
        frontend_url = f"https://{frontend_domain}"
        api_url = f"https://{api_domain}"

        # CloudFormation export name helper — prod keeps existing names for backward compat
        def export_name(suffix):
            if is_prod:
                return f"RssReader{suffix}"
            return f"RssReader{env_name.capitalize()}{suffix}"

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
        #     --secret-id <AppSecretArn> \
        #     --secret-string '{
        #       "GOOGLE_CLIENT_ID": "...",
        #       "GOOGLE_CLIENT_SECRET": "...",
        #       "JWT_SECRET": "<random-string>"
        #     }'
        app_secret = secretsmanager.Secret(
            self,
            "AppSecret",
            description=(
                f"RSS Reader ({env_name}) secrets: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET. "  # noqa: E501
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

        # Frontend CloudFront certificate (must be in us-east-1):
        #   prod — import the existing manually-created cert
        #   dev  — CDK provisions and validates via DNS
        if is_prod:
            frontend_certificate = acm.Certificate.from_certificate_arn(
                self,
                "Certificate",
                f"arn:aws:acm:us-east-1:{self.account}:certificate/{CERTIFICATE_ID}",
            )
        else:
            frontend_certificate = acm.Certificate(
                self,
                "FrontendCertificate",
                domain_name=frontend_domain,
                validation=acm.CertificateValidation.from_dns(zone),
            )

        # API custom domain certificate — CDK provisions and validates via DNS
        api_certificate = acm.Certificate(
            self,
            "ApiCertificate",
            domain_name=api_domain,
            validation=acm.CertificateValidation.from_dns(zone),
        )

        dashboard_name = "RssReader" if is_prod else f"RssReader-{env_name}"

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
                "REDIRECT_URI": f"{api_url}/auth/callback",
                "FRONTEND_URL": frontend_url,
                "APP_VERSION": APP_VERSION,
                "DASHBOARD_NAME": dashboard_name,
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

        # ── API Gateway custom domain ─────────────────────────────────────────
        api_domain_name = apigw.DomainName(
            self,
            "ApiDomainName",
            domain_name=api_domain,
            certificate=api_certificate,
            endpoint_type=apigw.EndpointType.EDGE,
            mapping=rest_api,
        )

        route53.ARecord(
            self,
            "ApiARecord",
            zone=zone,
            record_name=api_domain.removesuffix(".warlordofmars.net"),
            target=route53.RecordTarget.from_alias(
                r53_targets.ApiGatewayDomain(api_domain_name)
            ),
        )

        # ── EventBridge scheduler (every 30 min) ──────────────────────────────
        rule = events.Rule(
            self,
            "FeedRefreshRule",
            schedule=events.Schedule.rate(Duration.minutes(30)),
            description=f"Trigger RSS feed refresh every 30 minutes ({env_name})",
        )
        rule.add_target(targets.LambdaFunction(api_fn))

        # ── Frontend: S3 + CloudFront + Route53 ───────────────────────────────
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
            domain_names=[frontend_domain],
            certificate=frontend_certificate,
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

        route53.ARecord(
            self,
            "FrontendARecord",
            zone=zone,
            record_name=frontend_domain.removesuffix(".warlordofmars.net"),
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
                        environment={
                            "VITE_API_URL": api_url,
                            "VITE_APP_VERSION": APP_VERSION,
                        },
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
        # The OIDC provider is a singleton per AWS account — only prod creates it.
        # Dev references the provider by its deterministic ARN.
        if is_prod:
            github_oidc = iam.OpenIdConnectProvider(
                self,
                "GitHubOidcProvider",
                url="https://token.actions.githubusercontent.com",
                client_ids=["sts.amazonaws.com"],
            )
            oidc_provider_arn = github_oidc.open_id_connect_provider_arn
        else:
            # Provider was created by the prod stack; reference it by ARN
            oidc_provider_arn = (
                f"arn:aws:iam::{self.account}:oidc-provider"
                "/token.actions.githubusercontent.com"
            )

        deploy_role = iam.Role(
            self,
            "GitHubActionsDeployRole",
            assumed_by=iam.WebIdentityPrincipal(
                oidc_provider_arn,
                conditions={
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": (
                            f"repo:{GITHUB_REPO}:*"
                        ),
                    },
                },
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
            ],
            description=f"Assumed by GitHub Actions to deploy the RSS Reader CDK stack ({env_name})",  # noqa: E501
        )

        # ── CloudWatch Dashboard ──────────────────────────────────────────────
        dashboard = cw.Dashboard(
            self,
            "Dashboard",
            dashboard_name=dashboard_name,
        )

        # Lambda widgets
        dashboard.add_widgets(
            cw.TextWidget(markdown="## Lambda", width=24, height=1),
            cw.GraphWidget(
                title="Invocations & Errors",
                left=[
                    api_fn.metric_invocations(statistic="sum", period=Duration.minutes(5)),
                ],
                right=[
                    api_fn.metric_errors(statistic="sum", period=Duration.minutes(5)),
                ],
                width=12,
            ),
            cw.GraphWidget(
                title="Duration (p50 / p99)",
                left=[
                    api_fn.metric_duration(statistic="p50", period=Duration.minutes(5)),
                    api_fn.metric_duration(statistic="p99", period=Duration.minutes(5)),
                ],
                width=12,
            ),
            cw.GraphWidget(
                title="Throttles & Concurrent Executions",
                left=[
                    api_fn.metric_throttles(statistic="sum", period=Duration.minutes(5)),
                ],
                right=[
                    cw.Metric(
                        namespace="AWS/Lambda",
                        metric_name="ConcurrentExecutions",
                        dimensions_map={"FunctionName": api_fn.function_name},
                        statistic="max",
                        period=Duration.minutes(5),
                    ),
                ],
                width=12,
            ),
        )

        # API Gateway widgets
        dashboard.add_widgets(
            cw.TextWidget(markdown="## API Gateway", width=24, height=1),
            cw.GraphWidget(
                title="Request Count",
                left=[
                    cw.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Count",
                        dimensions_map={"ApiName": rest_api.rest_api_name},
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                ],
                width=8,
            ),
            cw.GraphWidget(
                title="4xx / 5xx Errors",
                left=[
                    cw.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="4XXError",
                        dimensions_map={"ApiName": rest_api.rest_api_name},
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                    cw.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="5XXError",
                        dimensions_map={"ApiName": rest_api.rest_api_name},
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                ],
                width=8,
            ),
            cw.GraphWidget(
                title="Latency (p50 / p99)",
                left=[
                    cw.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        dimensions_map={"ApiName": rest_api.rest_api_name},
                        statistic="p50",
                        period=Duration.minutes(5),
                    ),
                    cw.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        dimensions_map={"ApiName": rest_api.rest_api_name},
                        statistic="p99",
                        period=Duration.minutes(5),
                    ),
                ],
                width=8,
            ),
        )

        # DynamoDB widgets
        dashboard.add_widgets(
            cw.TextWidget(markdown="## DynamoDB", width=24, height=1),
            cw.GraphWidget(
                title="Consumed Read / Write Capacity",
                left=[
                    cw.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ConsumedReadCapacityUnits",
                        dimensions_map={"TableName": table.table_name},
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                ],
                right=[
                    cw.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ConsumedWriteCapacityUnits",
                        dimensions_map={"TableName": table.table_name},
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                ],
                width=12,
            ),
            cw.GraphWidget(
                title="Throttled Requests",
                left=[
                    cw.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ReadThrottleEvents",
                        dimensions_map={"TableName": table.table_name},
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                    cw.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="WriteThrottleEvents",
                        dimensions_map={"TableName": table.table_name},
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                ],
                width=12,
            ),
        )

        # CloudFront widgets
        dashboard.add_widgets(
            cw.TextWidget(markdown="## CloudFront", width=24, height=1),
            cw.GraphWidget(
                title="Requests",
                left=[
                    cw.Metric(
                        namespace="AWS/CloudFront",
                        metric_name="Requests",
                        dimensions_map={"DistributionId": distribution.distribution_id, "Region": "Global"},  # noqa: E501
                        statistic="sum",
                        period=Duration.minutes(5),
                    ),
                ],
                width=8,
            ),
            cw.GraphWidget(
                title="Cache Hit Rate",
                left=[
                    cw.Metric(
                        namespace="AWS/CloudFront",
                        metric_name="CacheHitRate",
                        dimensions_map={"DistributionId": distribution.distribution_id, "Region": "Global"},  # noqa: E501
                        statistic="average",
                        period=Duration.minutes(5),
                    ),
                ],
                width=8,
            ),
            cw.GraphWidget(
                title="4xx / 5xx Error Rate",
                left=[
                    cw.Metric(
                        namespace="AWS/CloudFront",
                        metric_name="4xxErrorRate",
                        dimensions_map={"DistributionId": distribution.distribution_id, "Region": "Global"},  # noqa: E501
                        statistic="average",
                        period=Duration.minutes(5),
                    ),
                    cw.Metric(
                        namespace="AWS/CloudFront",
                        metric_name="5xxErrorRate",
                        dimensions_map={"DistributionId": distribution.distribution_id, "Region": "Global"},  # noqa: E501
                        statistic="average",
                        period=Duration.minutes(5),
                    ),
                ],
                width=8,
            ),
        )

        CfnOutput(
            self,
            "DashboardUrl",
            value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home#dashboards:name={dashboard_name}",  # noqa: E501
            export_name=export_name("DashboardUrl"),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "TableName", value=table.table_name, export_name=export_name("TableName"))
        CfnOutput(
            self,
            "ContentBucketName",
            value=content_bucket.bucket_name,
            export_name=export_name("ContentBucketName"),
        )
        CfnOutput(
            self,
            "ContentBucketArn",
            value=content_bucket.bucket_arn,
            export_name=export_name("ContentBucketArn"),
        )
        CfnOutput(
            self,
            "ApiUrl",
            value=rest_api.url,
            export_name=export_name("ApiUrl"),
        )
        CfnOutput(
            self,
            "AppSecretArn",
            value=app_secret.secret_arn,
            description="Populate via ARN: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET",
            export_name=export_name("AppSecretArn"),
        )
        CfnOutput(
            self,
            "LambdaFunctionName",
            value=api_fn.function_name,
            export_name=export_name("LambdaFunctionName"),
        )
        CfnOutput(
            self,
            "FrontendBucketName",
            value=frontend_bucket.bucket_name,
            export_name=export_name("FrontendBucketName"),
        )
        CfnOutput(
            self,
            "FrontendDistributionId",
            value=distribution.distribution_id,
            export_name=export_name("FrontendDistributionId"),
        )
        CfnOutput(
            self,
            "FrontendUrl",
            value=frontend_url,
            export_name=export_name("FrontendUrl"),
        )
        CfnOutput(
            self,
            "ApiCustomDomain",
            value=api_url,
            export_name=export_name("ApiCustomDomain"),
        )
        CfnOutput(
            self,
            "GitHubActionsDeployRoleArn",
            value=deploy_role.role_arn,
            description="Set as AWS_DEPLOY_ROLE_ARN (prod) or AWS_DEV_DEPLOY_ROLE_ARN (dev) in GitHub Actions secrets",  # noqa: E501
            export_name=export_name("GitHubActionsDeployRoleArn"),
        )
