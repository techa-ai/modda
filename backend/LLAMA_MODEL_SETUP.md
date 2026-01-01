# Llama Model Setup Guide

## Current Status: Llama 4 Availability

**Important:** As of December 2024, Llama 4 Maverick may not be publicly available in AWS Bedrock yet. The model was announced for release in April 2025.

## Model ID Options

### Option 1: Llama 4 Maverick 17B (When Available)
```python
model_id = "meta.llama4-maverick-17b-instruct-v1:0"
# Global inference profile (when available)
global_model_id = "global.meta.llama4-maverick-17b-instruct-v1:0"
```

**Status:** Not yet available (expected April 2025)

### Option 2: Llama 3.3 70B (Currently Available - RECOMMENDED)
```python
# Regional model ID
model_id = "meta.llama3-3-70b-instruct-v1:0"
# Cross-region inference profile
global_model_id = "us.meta.llama3-3-70b-instruct-v1:0"
```

**Status:** ✅ Available now in AWS Bedrock

**Capabilities:**
- 70B parameters (dense model, not MoE)
- 128K context window
- Text-only (no native vision support)
- Cost-effective
- Strong performance on reasoning tasks

### Option 3: Llama 3.2 90B Vision (Currently Available)
```python
model_id = "meta.llama3-2-90b-instruct-v1:0"
global_model_id = "us.meta.llama3-2-90b-instruct-v1:0"
```

**Status:** ✅ Available now in AWS Bedrock

**Capabilities:**
- 90B parameters
- **Vision support** (can process images) ✅
- 128K context window
- Good for multimodal tasks (text + images)

### Option 4: Llama 3.2 11B Vision (Currently Available)
```python
model_id = "meta.llama3-2-11b-instruct-v1:0"
global_model_id = "us.meta.llama3-2-11b-instruct-v1:0"
```

**Status:** ✅ Available now

**Capabilities:**
- 11B parameters (smaller, faster)
- **Vision support** ✅
- 128K context window
- More cost-effective than 90B

## Recommended Approach for Now

Since we need vision capabilities to process 1008 forms (PDF → images), use:

**Llama 3.2 90B Vision Instruct** for best quality, or  
**Llama 3.2 11B Vision Instruct** for faster/cheaper processing

## How to Update the Comparison Script

Edit `compare_opus_vs_llama.py`:

```python
# At the top of the file, change:
# LLAMA_MODEL_ID = "global.meta.llama4-maverick-17b-instruct-v1:0"

# To one of:
LLAMA_MODEL_ID = "us.meta.llama3-2-90b-instruct-v1:0"  # Best quality
# OR
LLAMA_MODEL_ID = "us.meta.llama3-2-11b-instruct-v1:0"  # Faster/cheaper
```

## API Format Differences

### Llama 3.2 Vision API Format
```python
# Llama 3.2 uses standard Bedrock Messages API (similar to Claude)
{
    "anthropic_version": "bedrock-2023-05-31",  # Same API version
    "max_tokens": 16000,
    "temperature": 0.0,
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this document..."},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": "<base64_image>"
                    }
                }
            ]
        }
    ]
}
```

### Llama 4 Maverick API Format (Future)
```python
# Llama 4 may use a different format - TBD
{
    "prompt": "...",
    "images": ["<base64>", ...],
    "max_gen_len": 16000,
    "temperature": 0.0
}
```

## Updating the Code

I'll update the comparison scripts to:
1. Use Llama 3.2 90B Vision as the default
2. Add configuration option to switch models
3. Handle both API formats

## Model Comparison Matrix

| Model | Parameters | Vision | Context | Cost (Input/1M tokens) | Availability |
|-------|-----------|--------|---------|------------------------|--------------|
| Claude Opus 4.5 | ? | ✅ | 200K | ~$15 | ✅ Available |
| Llama 4 Maverick | 17B active (400B total) | ✅ | 1M | ~$0.14 | ❌ Not yet |
| Llama 3.3 70B | 70B | ❌ | 128K | ~$0.60 | ✅ Available |
| Llama 3.2 90B Vision | 90B | ✅ | 128K | ~$1.00 | ✅ Available |
| Llama 3.2 11B Vision | 11B | ✅ | 128K | ~$0.15 | ✅ Available |

## Next Steps

1. **Immediate:** Update scripts to use Llama 3.2 90B Vision
2. **Test:** Run comparison with available models
3. **Monitor:** Watch for Llama 4 Maverick availability
4. **Future:** Switch to Llama 4 when available for better performance

## Checking Model Availability

To check what models are available in your AWS account:

```bash
# Using AWS CLI
aws bedrock list-foundation-models \
    --region us-east-1 \
    --query 'modelSummaries[?contains(modelId, `llama`)].{ModelId:modelId, ModelName:modelName}' \
    --output table
```

Or use the AWS Bedrock Console:
https://console.aws.amazon.com/bedrock/home?region=us-east-1#/models




