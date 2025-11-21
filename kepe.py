import os
from openai import OpenAI


def get_client() -> OpenAI:
    """Return an OpenAI client configured with the API key from the environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export your key as an environment variable "
            "instead of hard-coding it in the repository."
        )
    return OpenAI(api_key=api_key)


def main() -> None:
    client = get_client()
    response = client.responses.create(
        model="gpt-5-nano",
        input="write a haiku about ai",
        store=True,
    )
    print(response.output_text)


if __name__ == "__main__":
    main()
