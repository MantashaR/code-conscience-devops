variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "availability_zones" {
  description = "AZs for the multi-AZ public subnets. Must be at least two for spec compliance."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least two availability zones are required."
  }
}

variable "localstack_endpoint" {
  description = <<-EOT
    LocalStack endpoint URL. Empty string targets real AWS using the normal
    credential chain. Default points at a local Docker LocalStack instance so
    that `terraform apply` works out of the box on a developer laptop.
  EOT
  type        = string
  default     = "http://localhost:4566"
}

variable "project" {
  description = "Value for the Project tag applied to every resource."
  type        = string
  default     = "nimbuskart"
}

variable "environment" {
  description = "Value for the Environment tag (e.g. staging, prod). Also suffixes the S3 bucket name."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "prod", "dev", "qa"], var.environment)
    error_message = "Environment must be one of: staging, prod, dev, qa."
  }
}

variable "owner" {
  description = "Value for the Owner tag (a team alias or individual)."
  type        = string
  default     = "platform-team"
}

variable "ssh_allowed_cidrs" {
  description = "Inbound CIDR blocks on TCP/22. Default is RFC1918 only; see Decisions & deviations."
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "ec2_ami_id" {
  description = <<-EOT
    AMI ID used by the web-tier EC2 instances. LocalStack accepts any string
    here because it does not actually boot VMs. For real AWS, replace with an
    SSM-resolved Amazon Linux 2023 AMI via a data source.
  EOT
  type        = string
  default     = "ami-0c55b159cbfafe1f0"
}

variable "ec2_instance_type" {
  description = "Instance type for the web tier."
  type        = string
  default     = "t3.micro"
}

variable "ec2_instance_count" {
  description = "Number of EC2 instances in the web tier (spec: two)."
  type        = number
  default     = 2

  validation {
    condition     = var.ec2_instance_count >= 1
    error_message = "At least one web instance is required."
  }
}

variable "logs_bucket_name_prefix" {
  description = "Prefix used to form the application-logs S3 bucket name. The bucket name will be '<prefix>-<environment>'."
  type        = string
  default     = "nimbuskart-app-logs"
}

variable "orphan_ebs_size_gb" {
  description = "Size of the intentionally-unattached EBS volume used as Janitor bait, in GB."
  type        = number
  default     = 20
}

variable "enable_lifecycle" {
  description = <<-EOT
    Whether to create the S3 bucket lifecycle configuration.

    Default: true. Set to false ONLY when targeting LocalStack in CI — the
    AWS provider 5.x waits on a consistency check (polling
    GetBucketLifecycleConfiguration until the response matches what was
    just put) that LocalStack 3's S3 emulation never satisfies, causing
    terraform apply to hang for 3 minutes and time out. Production
    deployments (real AWS) leave this as true.
  EOT
  type        = bool
  default     = true
}
