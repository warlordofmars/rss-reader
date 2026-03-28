import aws_cdk as cdk

from stacks.rss_reader_stack import RssReaderStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

RssReaderStack(app, "RssReaderStack", env=env)

app.synth()
