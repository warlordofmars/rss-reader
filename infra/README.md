# Infra

AWS CDK (Python) stack for the RSS Reader. All infrastructure is defined in a single stack: `RssReaderStack`.

## Commands

```bash
uv run inv synth    # synthesize CloudFormation template (no Docker bundling)
uv run inv deploy   # deploy to AWS
uv run inv outputs  # print stack outputs (URLs, table name, bucket, role ARN)
```

Or directly via CDK:

```bash
uv run cdk synth --no-staging -c account=<account-id>
uv run cdk deploy -c account=<account-id>
```

## First-time setup

```bash
# 1. Bootstrap CDK (once per account/region)
uv run cdk bootstrap -c account=<account-id>

# 2. Deploy
uv run inv deploy

# 3. Populate Secrets Manager (use AppSecretArn from outputs)
aws secretsmanager put-secret-value \
  --secret-id <AppSecretArn> \
  --secret-string '{"GOOGLE_CLIENT_ID":"...","GOOGLE_CLIENT_SECRET":"...","JWT_SECRET":"..."}'
```

## Stack resources

| Resource | Description |
| --- | --- |
| DynamoDB table | Single-table design with GSI1 (scheduler) and GSI2 (user articles) |
| S3 `ArticleContentBucket` | Stores article content > 300KB; `RETAIN` on stack deletion |
| Secrets Manager `AppSecret` | Google OAuth + JWT secrets; populated manually after first deploy |
| Lambda `ApiFunction` | Python 3.13, 512MB, 30s timeout; Docker-bundled at deploy time |
| API Gateway `RestApi` | Edge-optimised REST API proxying all requests to Lambda |
| API Gateway custom domain | `api.rss.warlordofmars.net` with ACM certificate |
| EventBridge rule | Triggers Lambda every 30 minutes to refresh feeds |
| S3 `FrontendBucket` | Private bucket serving frontend assets via CloudFront |
| CloudFront distribution | HTTPS, SPA routing (403/404 → `index.html`) |
| Route53 records | `rss.warlordofmars.net` → CloudFront, `api.rss.warlordofmars.net` → API Gateway |
| OIDC provider + deploy role | Allows GitHub Actions to deploy without long-lived AWS keys |

## Adding resources

All resources are defined in `stacks/rss_reader_stack.py`. After editing:

1. Run `uv run inv synth` to validate
2. Open a PR — the `Infra (lint + synth)` CI job will catch any synthesis errors
3. Merging to `main` triggers an automatic deploy
