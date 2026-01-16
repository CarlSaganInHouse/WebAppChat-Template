# WebAppChat Alexa Skill Example

Ready-to-deploy AWS Lambda function for integrating WebAppChat with Amazon Alexa.

## Quick Start

### 1. Package Lambda Function

```bash
cd examples/alexa-skill
pip install -r requirements.txt -t .
zip -r lambda-deployment.zip lambda_function.py ask_sdk_core/ requests/ urllib3/ certifi/ charset_normalizer/ idna/
```

### 2. Deploy to AWS Lambda

**Via AWS Console:**
1. Go to AWS Lambda Console
2. Create function → Author from scratch
3. Function name: `webappchat-alexa`
4. Runtime: Python 3.11
5. Upload `lambda-deployment.zip`

**Via AWS CLI:**
```bash
aws lambda create-function \
  --function-name webappchat-alexa \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda-deployment.zip \
  --timeout 30 \
  --memory-size 256 \
  --environment Variables="{
    WEBAPPCHAT_URL=https://your-domain.com,
    WEBAPPCHAT_API_KEY=your-api-key-here,
    DEFAULT_MODEL=gpt-4o-mini,
    USE_RAG=true
  }"
```

### 3. Configure Environment Variables

In Lambda console, set:
- `WEBAPPCHAT_URL`: Your WebAppChat URL (e.g., `https://your-domain.com`)
- `WEBAPPCHAT_API_KEY`: API key from WebAppChat
- `DEFAULT_MODEL`: (Optional) Default model, defaults to `gpt-4o-mini`
- `USE_RAG`: (Optional) Enable RAG, defaults to `true`

### 4. Add Alexa Trigger

1. In Lambda console, click "Add trigger"
2. Select "Alexa Skills Kit"
3. Paste your Skill ID (from Alexa Developer Console)
4. Click "Add"

### 5. Create Alexa Skill

1. Go to https://developer.amazon.com/alexa/console/ask
2. Create Skill → Custom → Provision your own
3. Skill name: "WebAppChat"
4. Go to **JSON Editor** and paste contents of `interaction-model.json`
5. Save and Build Model
6. Go to **Endpoint** → AWS Lambda ARN
7. Paste your Lambda ARN: `arn:aws:lambda:us-east-1:123456789:function:webappchat-alexa`

### 6. Test

In Alexa Developer Console → Test tab:

```
Alexa, open web chat
> What's the weather like?

Alexa, ask web chat about my meeting notes
> Tell me about quantum computing
```

## Files

- `lambda_function.py` - Main Lambda handler
- `requirements.txt` - Python dependencies
- `interaction-model.json` - Alexa interaction model (voice interface)
- `README.md` - This file

## Commands

**Launch:**
- "Alexa, open web chat"
- "Alexa, start web chat"

**Ask questions:**
- "Alexa, ask web chat what is Python"
- "Alexa, ask web chat to explain quantum computing"
- "Alexa, ask web chat about my daily notes"

**Stop:**
- "Alexa, stop"
- "Alexa, cancel"

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WEBAPPCHAT_URL` | Yes | - | WebAppChat base URL |
| `WEBAPPCHAT_API_KEY` | Yes | - | API key for authentication |
| `DEFAULT_MODEL` | No | `gpt-4o-mini` | Default LLM model |
| `USE_RAG` | No | `true` | Enable RAG by default |
| `MAX_SPEECH_LENGTH` | No | `6000` | Max chars for speech output |
| `REQUEST_TIMEOUT` | No | `30` | API request timeout (seconds) |

### Lambda Settings

- **Timeout**: 30 seconds (allows time for LLM response)
- **Memory**: 256 MB (sufficient for this workload)
- **Runtime**: Python 3.11

## Troubleshooting

### "I'm having trouble with that skill"

Check CloudWatch logs:
```bash
aws logs tail /aws/lambda/webappchat-alexa --follow
```

Common causes:
- Lambda timeout (increase to 30s)
- Invalid API key
- WebAppChat endpoint unreachable
- Missing environment variables

### Test Lambda Directly

```bash
aws lambda invoke \
  --function-name webappchat-alexa \
  --payload file://test-event.json \
  response.json

cat response.json
```

### Test API Key

```bash
curl -X POST https://your-domain.com/ask \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test"}'
```

## Cost Estimate

**Per 1000 conversations:**
- AWS Lambda: ~$0.05
- LLM API calls: ~$1-10 (varies by model)
- **Total: ~$1-10/month for typical usage**

## Next Steps

1. Test in development mode
2. Add more intents (see main docs)
3. Implement session persistence with DynamoDB
4. Add usage tracking
5. Submit for Alexa Skills Store certification

## Resources

- [Full Integration Guide](../../docs/ALEXA_INTEGRATION.md)
- [WebAppChat API Docs](../../docs/API.md)
- [Alexa Skills Kit Docs](https://developer.amazon.com/docs/ask-overviews/build-skills-with-the-alexa-skills-kit.html)
