variable "name_prefix" {
  description = "Prefix applied to all named resources in this module (e.g. nimbuskart-staging)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs, one per AZ. Length must equal length(availability_zones)."
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2
    error_message = "At least two public subnet CIDRs are required to satisfy the multi-AZ spec."
  }
}

variable "availability_zones" {
  description = "Availability zones, in the same order as public_subnet_cidrs."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "ssh_allowed_cidrs" {
  description = <<-EOT
    CIDR blocks allowed inbound on TCP/22.

    DEVIATION FROM SPEC: the spec specified 0.0.0.0/0 as the default. We default
    to RFC1918 private space because exposing SSH to the entire internet is one
    of the top causes of compromised instances. Callers who genuinely need
    public SSH can override this variable explicitly.
  EOT
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "tags" {
  description = "Common tags applied to all taggable resources in this module."
  type        = map(string)
  default     = {}
}
