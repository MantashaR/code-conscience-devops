"""
Pricing constants for orphan cost estimation.

All numbers are on-demand list prices in us-east-1, retrieved 2026-05-22 from
the AWS pricing pages. Real waste is typically *higher* than these estimates
because orphans don't benefit from reserved-instance or savings-plan discounts
that the rest of the account does — but they're a reasonable conservative
lower bound to surface in a report.

Sources:
- EBS gp3:                 https://aws.amazon.com/ebs/pricing/
                           (us-east-1, $0.08 per GB-month)
- Elastic IP unassociated: https://aws.amazon.com/vpc/pricing/
                           ($0.005 per hour while not attached to a running instance)

Stopped-instance estimates account only for the root EBS volume that survives
a stop. Compute charges go to $0 while stopped, but a long-stopped instance
is still waste because (a) its root volume keeps billing, (b) it almost
always signals abandoned work, and (c) it accumulates patch/CVE risk that
operations teams pay for in other ways.
"""

# EBS gp3 per-GB monthly price (us-east-1).
EBS_GP3_USD_PER_GB_MONTH = 0.08

# Assumed root-volume size for a stopped instance whose actual size we don't
# resolve. 8 GB is the AL2023 default.
STOPPED_INSTANCE_ROOT_VOLUME_GB = 8
STOPPED_INSTANCE_MONTHLY_USD = (
    STOPPED_INSTANCE_ROOT_VOLUME_GB * EBS_GP3_USD_PER_GB_MONTH
)

# Elastic IP not associated with a running instance: $0.005/hour. Converted to
# a 30-day month for the report.
EIP_UNASSOCIATED_HOURLY_USD = 0.005
EIP_UNASSOCIATED_MONTHLY_USD = EIP_UNASSOCIATED_HOURLY_USD * 24 * 30  # ~$3.60

# Required tags every resource must carry. Anything missing one or more of
# these will be reported as `missing_required_tags`.
REQUIRED_TAGS = ("Project", "Environment", "Owner")

# Tag that exempts a resource from --delete mode entirely.
PROTECTED_TAG_KEY = "Protected"
PROTECTED_TAG_VALUE = "true"
