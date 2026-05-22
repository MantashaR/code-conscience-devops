################################################################################
# NimbusKart staging — root module.
#
# Composes the network module and adds the web tier (EC2), application-logs
# bucket (S3 with versioning + non-current expiration), and one deliberately-
# unattached EBS volume used as bait for the Cost Janitor in Part B.
################################################################################

locals {
  name_prefix = "${var.project}-${var.environment}"

  # Required tags per spec. Every taggable resource in this stack merges
  # these in. ManagedBy is fixed to "terraform" because the spec says so and
  # it would be a lie otherwise.
  common_tags = {
    Project     = var.project
    Environment = var.environment
    Owner       = var.owner
    ManagedBy   = "terraform"
  }
}

module "network" {
  source = "./modules/network"

  name_prefix        = local.name_prefix
  availability_zones = var.availability_zones
  ssh_allowed_cidrs  = var.ssh_allowed_cidrs
  tags               = local.common_tags
}

################################################################################
# Web tier.
################################################################################

resource "aws_instance" "web" {
  count = var.ec2_instance_count

  ami                    = var.ec2_ami_id
  instance_type          = var.ec2_instance_type
  subnet_id              = module.network.public_subnet_ids[count.index % length(module.network.public_subnet_ids)]
  vpc_security_group_ids = [module.network.web_security_group_id]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-web-${count.index}"
    Tier = "web"
  })
}

################################################################################
# Application-logs S3 bucket.
#
# Versioning is enabled. A lifecycle rule expires non-current versions after
# 30 days — this is what bounds the cost growth of the bucket. The current
# version is retained indefinitely.
################################################################################

resource "aws_s3_bucket" "logs" {
  bucket = "${var.logs_bucket_name_prefix}-${var.environment}"

  tags = merge(local.common_tags, {
    Name    = "${var.logs_bucket_name_prefix}-${var.environment}"
    Purpose = "application-logs"
  })
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    # Empty filter {} crashes LocalStack 3's S3 lifecycle parser; an explicit
    # zero-length prefix means "every object" and survives the round-trip.
    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  depends_on = [aws_s3_bucket_versioning.logs]
}

################################################################################
# Orphan EBS volume.
#
# Deliberately not attached to anything. Part B's Cost Janitor is expected to
# flag this as an "available" (orphaned) volume on every scan. The
# Purpose tag makes its intent obvious to a future maintainer who finds it.
################################################################################

resource "aws_ebs_volume" "orphan" {
  availability_zone = var.availability_zones[0]
  size              = var.orphan_ebs_size_gb
  type              = "gp3"

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-orphan-volume"
    Purpose = "intentionally-unattached-janitor-bait"
  })
}
