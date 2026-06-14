# Currency Rate Service — Python Lambda

A Python rewrite of a Spring Boot currency rates API, designed for minimal AWS Lambda cold-start time. The service exposes a single endpoint (`GET /api/rates`) that proxies and caches exchange rates from an upstream provider.

## Architecture

```
Client
  └─► CloudFront (5-minute edge cache, 24-hour stale-if-error)
        └─► API Gateway (HTTP API v2)
              └─► Lambda (Python 3.13)
                    └─► allratestoday.com /api/v1/rates
```

On upstream failure the Lambda returns the last successfully fetched rates from its in-memory cache with an `X-Rates-Stale: true` response header. CloudFront independently serves its own cached copy for up to 24 hours when the origin returns 5xx or is unreachable.

## Technical Background

| Concern | Approach |
|---|---|
| Runtime | Python 3.13, no web framework — direct API Gateway HTTP API v2 event handling |
| HTTP client | `requests` (the only runtime dependency) |
| Cold start | Module-level singletons initialized once per container; warm invocations skip all initialization |
| In-memory cache | Thread-safe (`threading.Lock`) `RatesCache`; holds the last successful upstream response for stale-fallback |
| Error handling | `ExternalApiException` (HTTP 4xx/5xx) and `NetworkException` (connection/timeout) map to RFC 9457 `application/problem+json` 503 responses |
| Rate precision | `decimal.Decimal` used internally; serialized as JSON numbers via `float` |
| Rate ordering | Response `rates` map is always sorted ascending by currency code (matches upstream Java TreeMap behavior) |
| Duplicate currencies | First occurrence wins when the upstream returns duplicate target currency codes |

## Project Structure

```
cs-lambda/
├── handler.py                  # Lambda entry point — lambda_handler(event, context)
├── src/
│   ├── config.py               # Config dataclass (reads env vars)
│   ├── currency_service.py     # Business logic — fetch, transform, cache
│   ├── exceptions.py           # ExternalApiException, NetworkException
│   ├── models.py               # CurrencyRatesResponse, RatesFetchResult
│   └── rates_cache.py          # Thread-safe in-memory stale-fallback cache
├── tests/
│   ├── conftest.py             # Shared fixtures and helpers
│   ├── test_currency_service.py  # Unit tests (14) — mocked HTTP via responses
│   ├── test_exception_handler.py # Exception-to-response mapping tests (10)
│   ├── test_handler.py           # Route handler tests (7)
│   ├── test_integration.py       # Full-stack integration tests (5)
│   └── test_rates_cache.py       # Cache unit tests (5)
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Runtime + test dependencies
└── pyproject.toml              # pytest and coverage configuration
```

## API

### `GET /api/rates`

Returns the latest exchange rates sourced from USD.

**Success — 200 OK**

```http
Content-Type: application/json
Cache-Control: public, max-age=300, stale-if-error=86400
```

```json
{
  "success": true,
  "source": "USD",
  "date": "2026-06-09T04:33:00+0000",
  "rates": {
    "EUR": 0.9235,
    "GBP": 0.7885,
    "JPY": 154.32
  }
}
```

The `X-Rates-Stale: true` header is added when the upstream is unavailable and the response is being served from the Lambda's in-memory cache.

**Upstream API error — 503 Service Unavailable**

```http
Content-Type: application/problem+json
```

```json
{
  "type": "urn:currency-service:upstream-error",
  "title": "Upstream API Error",
  "status": 503,
  "detail": "The currency rates provider returned an error. Please retry shortly."
}
```

**Network error — 503 Service Unavailable**

```json
{
  "type": "urn:currency-service:network-error",
  "title": "Upstream Unreachable",
  "status": 503,
  "detail": "Unable to connect to the currency rates provider. Please retry shortly."
}
```

Error responses conform to [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) (Problem Details for HTTP APIs).

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CURRENCY_API_KEY` | **Yes** | *(empty)* | Bearer token for the upstream allratestoday.com API |
| `CURRENCY_API_BASE_URL` | No | `https://allratestoday.com` | Upstream API base URL |
| `CURRENCY_API_PATH` | No | `/api/v1/rates` | Upstream endpoint path |
| `CURRENCY_API_SOURCE` | No | `USD` | Base currency for rate conversion |
| `CURRENCY_API_CACHE_MAX_AGE` | No | `300` | `Cache-Control: max-age` value in seconds |
| `CURRENCY_API_STALE_IF_ERROR` | No | `86400` | `Cache-Control: stale-if-error` value in seconds |

`CURRENCY_API_KEY` is sent to the upstream as `Authorization: Bearer <key>` and is never logged or returned to clients.

## Local Setup

### Prerequisites

- Python 3.13+
- pip

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

### Configure the API Key

Create a `.env` file in the project root (git-ignored):

```bash
export CURRENCY_API_KEY=your_key_here
```

Source it before running:

```bash
source .env
```

Or set it inline when invoking the handler manually.

### Run Tests

```bash
pytest
```

This runs all 41 tests with coverage reporting:

```
Name                      Stmts   Miss  Cover
-----------------------------------------------
handler.py                   35      0   100%
src/config.py                10      0   100%
src/currency_service.py      43      0   100%
src/exceptions.py             5      0   100%
src/models.py                13      0   100%
src/rates_cache.py           16      0   100%
-----------------------------------------------
TOTAL                       122      0   100%
```

### Invoke the Handler Locally

```python
import os, json
os.environ["CURRENCY_API_KEY"] = "your_key_here"

from handler import lambda_handler

event = {
    "version": "2.0",
    "rawPath": "/api/rates",
    "requestContext": {"http": {"method": "GET", "path": "/api/rates"}},
}
response = lambda_handler(event, None)
print(json.dumps(json.loads(response["body"]), indent=2))
```

## AWS Setup

### 1. Package the Lambda

Create a deployment package containing the handler, source, and runtime dependencies:

```bash
# Install runtime dependencies into a staging directory
pip install -r requirements.txt --target ./package --upgrade

# Copy source code into the staging directory
cp -r src handler.py package/

# Zip it up
cd package && zip -r ../function.zip . && cd ..
```

### 2. Create the Lambda Function

```bash
aws lambda create-function \
  --function-name currency-service \
  --runtime python3.13 \
  --handler handler.lambda_handler \
  --zip-file fileb://function.zip \
  --role arn:aws:iam::<account-id>:role/<execution-role> \
  --timeout 30 \
  --memory-size 256 \
  --environment Variables="{CURRENCY_API_KEY=your_key_here}"
```

**Recommended settings:**

| Setting | Value | Reason |
|---|---|---|
| Runtime | `python3.13` | Matches development environment |
| Handler | `handler.lambda_handler` | Entry point |
| Memory | 256 MB | Sufficient; increase if cold starts are slow |
| Timeout | 30 s | Upstream request timeout is 29 s |
| Architecture | `arm64` | ~20% cheaper, same performance |

### 3. Update an Existing Function

```bash
# Update code
aws lambda update-function-code \
  --function-name currency-service \
  --zip-file fileb://function.zip

# Update environment variables
aws lambda update-function-configuration \
  --function-name currency-service \
  --environment Variables="{CURRENCY_API_KEY=your_key_here}"
```

### 4. Configure API Gateway (HTTP API v2)

Create an HTTP API with a Lambda integration and a route for `GET /api/rates`. The Lambda function receives and returns events in the [HTTP API v2 payload format](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html).

```bash
# Create the HTTP API
API_ID=$(aws apigatewayv2 create-api \
  --name currency-service \
  --protocol-type HTTP \
  --query ApiId --output text)

# Create the Lambda integration
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type AWS_PROXY \
  --integration-uri arn:aws:lambda:<region>:<account-id>:function:currency-service \
  --payload-format-version 2.0 \
  --query IntegrationId --output text)

# Create the route
aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key "GET /api/rates" \
  --target "integrations/$INTEGRATION_ID"

# Deploy to a stage
aws apigatewayv2 create-stage \
  --api-id $API_ID \
  --stage-name prod \
  --auto-deploy

# Grant API Gateway permission to invoke the Lambda
aws lambda add-permission \
  --function-name currency-service \
  --statement-id apigateway-invoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:<region>:<account-id>:$API_ID/*"
```

### 5. Deploy CloudFront (Optional but Recommended)

A CloudFormation template is provided at `infrastructure/cloudfront.yaml`. It creates:

- A CloudFront distribution with a 5-minute minimum TTL
- A cache policy that excludes all query strings, cookies, and custom headers from the cache key
- A `stale-if-error` window of 24 hours — CloudFront serves cached rates when the origin returns 5xx or is unreachable

```bash
aws cloudformation deploy \
  --template-file infrastructure/cloudfront.yaml \
  --stack-name currency-service-cdn \
  --parameter-overrides \
      ApiGatewayDomainName=<api-id>.execute-api.<region>.amazonaws.com \
      ApiGatewayStageName=prod
```

**Stack outputs:**

| Output | Description |
|---|---|
| `DistributionId` | Use with `aws cloudfront create-invalidation` to bust the cache |
| `DistributionDomainName` | CNAME your custom domain to this value in Route 53 |
| `CurrencyRatesEndpoint` | Direct URL to `GET /api/rates` via CloudFront |

**Cache invalidation:**

```bash
aws cloudfront create-invalidation \
  --distribution-id <DistributionId> \
  --paths "/api/rates"
```

### IAM Execution Role

The Lambda execution role requires only basic permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

No VPC, no S3, no DynamoDB — the service makes outbound HTTPS calls to the upstream API only.

## Runtime Dependencies

| Package | Version | Purpose |
|---|---|---|
| `requests` | ≥ 2.32.0 | HTTP client for upstream API calls |

## Development Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pytest` | ≥ 8.3.0 | Test runner |
| `pytest-cov` | ≥ 6.0.0 | Coverage reporting |
| `responses` | ≥ 0.25.3 | `requests` HTTP mock for unit and integration tests |
