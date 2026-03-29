import aws_cdk as cdk

from stacks.rss_reader_stack import RssReaderStack

app = cdk.App()

env_name = app.node.try_get_context("env") or "prod"
stack_id = "RssReaderStack" if env_name == "prod" else f"RssReaderStack-{env_name}"

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

RssReaderStack(app, stack_id, env_name=env_name, env=env)

app.synth()
