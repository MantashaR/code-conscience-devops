################################################################################
# AWS provider, parametrised so the same code targets LocalStack today and a
# real AWS account tomorrow.
#
# When var.localstack_endpoint is non-empty (default), the provider is wired
# for LocalStack: mock credentials, path-style S3, all relevant service
# endpoints overridden. Set var.localstack_endpoint = "" to target real AWS;
# normal AWS credential chain (env vars, profile, IRSA) then applies.
################################################################################

locals {
  use_localstack = var.localstack_endpoint != ""
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = local.use_localstack ? "mock-access-key" : null
  secret_key                  = local.use_localstack ? "mock-secret-key" : null
  skip_credentials_validation = local.use_localstack
  skip_metadata_api_check     = local.use_localstack
  skip_requesting_account_id  = local.use_localstack
  s3_use_path_style           = local.use_localstack

  dynamic "endpoints" {
    for_each = local.use_localstack ? [var.localstack_endpoint] : []
    content {
      ec2 = endpoints.value
      s3  = endpoints.value
      iam = endpoints.value
      sts = endpoints.value
      ebs = endpoints.value
    }
  }
}
