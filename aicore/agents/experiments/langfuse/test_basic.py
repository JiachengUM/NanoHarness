from langfuse import Langfuse
 
langfuse = Langfuse(
    secret_key="REDACTED",
    public_key="pk-lf-ab17d850-6d21-47cf-9150-af06622b8f0f",
    host="https://cloud.langfuse.com"
)
 
# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")


def test_basic(langfuse: Langfuse):

    trace = langfuse.trace(name="my-complex-workflow")

    # 第一层 Span
    span_l1 = trace.span(name="Level-1-Processing")

    # 第二层 Span (显式指定父级)
    span_l2 = langfuse.span(
        name="Level-2-SubTask",
        trace_id=trace.id,
        parent_observation_id=span_l1.id
    )

    # ... 执行任务 ...

    span_l2.end()
    span_l1.end()
    langfuse.flush()


if __name__ == "__main__":
    test_basic(langfuse)