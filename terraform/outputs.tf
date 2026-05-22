output "vpc_id" {
  description = "VPC ID."
  value       = module.network.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (in AZ order)."
  value       = module.network.public_subnet_ids
}

output "web_security_group_id" {
  description = "Security group ID protecting the web tier."
  value       = module.network.web_security_group_id
}

output "logs_bucket_name" {
  description = "Name of the application-logs S3 bucket."
  value       = aws_s3_bucket.logs.bucket
}

output "web_instance_ids" {
  description = "IDs of the web-tier EC2 instances."
  value       = aws_instance.web[*].id
}

output "orphan_ebs_volume_id" {
  description = "ID of the deliberately-unattached EBS volume (the Janitor's bait)."
  value       = aws_ebs_volume.orphan.id
}
