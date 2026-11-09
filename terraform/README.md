# Terraform: public HTTPS UI on EC2 (ap-south-1)

Deploys the Streamlit UI on EC2 behind an ALB with an ACM SSL cert, reachable at
`https://<subdomain>.<domain>`. The app reaches RDS **through the Teleport
tunnel** (tbot runs on the instance via IAM-join), so the box holds no DB
password — only outbound 443 to Teleport Cloud.

```
Internet ─HTTPS→ ALB (ACM) ─HTTP:8501→ EC2 (Streamlit + tbot) ─5433→ tbot ─443→ Teleport Cloud → RDS
```

## Prerequisites
- A domain you own (registered anywhere). You'll delegate it to Route53.
- `tsh login` active (to create the Teleport IAM-join token).
- AWS creds for account `123456789012`.

## One-time Teleport setup
Create the IAM-join token so the EC2 bot can join without a secret:
```bash
tctl create -f teleport-ec2-iam-token.yaml
```

## Deploy (two-phase, because of DNS delegation)

ACM validation needs your domain delegated to the new Route53 zone first.

**Phase 1 — create the hosted zone, get the name servers:**
```bash
cp terraform.tfvars.example terraform.tfvars   # set domain_name + subdomain
terraform init
terraform apply -target=aws_route53_zone.primary
terraform output name_servers
```
Copy those 4 name servers into your registrar's **NS records** for the domain.
Wait for propagation (minutes to a couple of hours):
```bash
dig +short NS <your-domain> @8.8.8.8     # should list the AWS ns-... servers
```

**Phase 2 — build everything else:**
```bash
terraform apply
```
ACM validation, the ALB, the cert, the EC2 instance, and the DNS alias all come
up. When it finishes:
```bash
terraform output url     # https://teleport-demo.<your-domain>
```

The instance takes ~3-4 min after boot to install deps and start the services.
Check health: ALB target should go `healthy`; then the URL serves the UI.

## Verify on the box (optional)
```bash
# via SSM (no SSH key needed)
aws ssm start-session --region ap-south-1 --target <ec2_instance_id>
sudo systemctl status tbot streamlit
sudo journalctl -u tbot -n 50          # should show "Successfully joined"
```

## Teardown
```bash
terraform destroy
tctl rm token/ec2-ui-iam-token
```

## Notes
- ALB ≈ \$16-20/mo; t3.small ≈ \$15/mo. Run `terraform destroy` after use.
- If you change `ec2_role_name`, update the ARN in `teleport-ec2-iam-token.yaml`.
- The EC2 bot reuses `agent-bot` (role `agent-db-readonly`), so the same
  least-privilege story applies — and the `:5434` super-user denial still holds.
