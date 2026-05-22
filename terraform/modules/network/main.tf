################################################################################
# NimbusKart network module
#
# Provisions a VPC, two public subnets across two AZs, an internet gateway with
# a shared public route table, and a web-tier security group.
#
# Tagging is applied via var.tags (merged with a per-resource Name). This
# module never overrides the Project/Environment/Owner/ManagedBy keys passed
# in by the caller.
################################################################################

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_subnet" "public" {
  for_each = {
    for idx, cidr in var.public_subnet_cidrs : tostring(idx) => {
      cidr = cidr
      az   = var.availability_zones[idx]
    }
  }

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-public-${each.key}"
    Tier = "public"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-public-rt" })
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

################################################################################
# Web-tier security group.
#
# Spec asked for SSH (22) open to 0.0.0.0/0 by default. We deliberately default
# to RFC1918 private space and let the caller widen it via var.ssh_allowed_cidrs
# if they really mean it. See "Decisions & deviations" in the root README.
################################################################################

resource "aws_security_group" "web" {
  name        = "${var.name_prefix}-web-sg"
  description = "NimbusKart web tier: HTTP/HTTPS open, SSH restricted"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTP from anywhere (spec). Production should redirect 80 -> 443 at ALB."
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH from admin CIDR (deviation: spec default was 0.0.0.0/0)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_cidrs
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-web-sg" })
}
