# Public hosted zone for your domain. Because the domain is registered
# elsewhere, you must copy the `name_servers` output into your registrar's
# NS records. ACM DNS validation only succeeds AFTER that delegation
# propagates (see README for the two-phase apply).
resource "aws_route53_zone" "primary" {
  name = var.domain_name
}

resource "aws_acm_certificate" "ui" {
  domain_name       = local.fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.ui.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id         = aws_route53_zone.primary.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "ui" {
  certificate_arn         = aws_acm_certificate.ui.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# The public URL -> ALB
resource "aws_route53_record" "ui_alias" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = local.fqdn
  type    = "A"

  alias {
    name                   = aws_lb.ui.dns_name
    zone_id                = aws_lb.ui.zone_id
    evaluate_target_health = true
  }
}
