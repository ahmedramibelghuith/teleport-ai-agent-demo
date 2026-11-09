# The existing VPC has only one public subnet (ap-south-1b). An internet-facing
# ALB needs >=2 public subnets in >=2 AZs, so we add two dedicated public
# subnets for this stack (10.0.10.0/24, 10.0.11.0/24) and route them to the
# existing Internet Gateway. We do NOT touch the existing RDS subnets.

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = var.vpc_id
  cidr_block              = cidrsubnet(data.aws_vpc.app.cidr_block, 8, 10 + count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.name_prefix}-public-${count.index}"
  }
}

resource "aws_route_table" "public" {
  vpc_id = var.vpc_id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = data.aws_internet_gateway.igw.id
  }

  tags = {
    Name = "${var.name_prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
