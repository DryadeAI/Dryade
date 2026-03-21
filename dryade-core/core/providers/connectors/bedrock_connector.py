"""AWS Bedrock connector for connection testing and model discovery."""

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector


class BedrockConnector(ProviderConnector):
    """AWS Bedrock connection testing.

    Uses boto3 to list foundation models. Requires AWS credentials
    configured via environment variables, AWS config file, or IAM role.

    API docs: https://docs.aws.amazon.com/bedrock/latest/userguide/models-get-info.html
    """

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to AWS Bedrock.

        Note: Bedrock uses AWS credentials (access key + secret), not a simple API key.
        The api_key parameter can be JSON-encoded credentials or left empty to use
        the default AWS credential chain (env vars, ~/.aws/credentials, IAM role).

        Args:
            api_key: Optional JSON string with AWS credentials:
                     {"access_key_id": "...", "secret_access_key": "...", "region": "..."}
                     If not provided, uses default AWS credential chain.
            endpoint: AWS region (e.g., "us-east-1"). Defaults to us-east-1.

        Returns:
            ConnectionTestResult with success status and available models
        """
        try:
            import json

            import boto3
            from botocore.exceptions import (
                ClientError,
                NoCredentialsError,
                PartialCredentialsError,
            )

            # Parse credentials if provided
            client_kwargs = {}
            region = base_url or "us-east-1"

            if api_key:
                try:
                    creds = json.loads(api_key)
                    client_kwargs = {
                        "aws_access_key_id": creds.get("access_key_id"),
                        "aws_secret_access_key": creds.get("secret_access_key"),
                        "region_name": creds.get("region", region),
                    }
                    if creds.get("session_token"):
                        client_kwargs["aws_session_token"] = creds["session_token"]
                except json.JSONDecodeError:
                    return ConnectionTestResult(
                        success=False,
                        message="Invalid credentials format. Expected JSON with access_key_id, secret_access_key, and optional region.",
                        error_code="invalid_format",
                    )
            else:
                client_kwargs["region_name"] = region

            # Create Bedrock client
            client = boto3.client("bedrock", **client_kwargs)

            # List foundation models
            response = client.list_foundation_models()
            model_summaries = response.get("modelSummaries", [])

            # Extract model IDs, filtering for text generation models
            models = []
            for model in model_summaries:
                model_id = model.get("modelId", "")
                output_modalities = model.get("outputModalities", [])
                # Include models that can generate text
                if "TEXT" in output_modalities:
                    models.append(model_id)

            return ConnectionTestResult(
                success=True,
                message=f"Connected to Bedrock ({region}). Found {len(models)} text models.",
                models=models[:30],  # Limit for display
            )

        except ImportError:
            return ConnectionTestResult(
                success=False,
                message="boto3 package not installed. Run: pip install boto3",
                error_code="missing_dependency",
            )
        except NoCredentialsError:
            return ConnectionTestResult(
                success=False,
                message="No AWS credentials found. Configure via environment variables, ~/.aws/credentials, or provide credentials JSON.",
                error_code="missing_credentials",
            )
        except PartialCredentialsError:
            return ConnectionTestResult(
                success=False,
                message="Incomplete AWS credentials. Both access_key_id and secret_access_key are required.",
                error_code="invalid_credentials",
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("InvalidSignatureException", "SignatureDoesNotMatch"):
                return ConnectionTestResult(
                    success=False,
                    message="Invalid AWS credentials (signature mismatch)",
                    error_code="invalid_key",
                )
            if error_code == "AccessDeniedException":
                return ConnectionTestResult(
                    success=False,
                    message="Access denied. Check IAM permissions for Bedrock.",
                    error_code="access_denied",
                )
            return ConnectionTestResult(
                success=False,
                message=f"AWS error: {e.response.get('Error', {}).get('Message', str(e))}",
                error_code="aws_error",
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
                error_code="connection_error",
            )

    async def discover_models(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> list[str]:
        """Discover available foundation models from AWS Bedrock.

        Returns list of model IDs that support text generation.
        """
        result = await self.test_connection(api_key, base_url)
        return result.models or []
