# Fix Llama 4 Maverick Permissions

## Problem

Llama 4 Maverick extraction fails with:
```
AccessDeniedException: User is not authorized to perform: bedrock:InvokeModel 
on resource: arn:aws:bedrock:us-east-1::foundation-model/meta.llama4-maverick-17b-instruct-v1:0
```

## Root Cause

Your IAM user (`arn:aws:iam::173737639904:user/BedrockAPIKey-hbsh`) has permissions for Claude models but **NOT** for Llama models.

## Solution

You need to add `bedrock:InvokeModel` permission for Llama models to your IAM user.

### Option 1: Add Llama to Existing IAM Policy

1. Go to IAM Console: https://console.aws.amazon.com/iam/
2. Find user: `BedrockAPIKey-hbsh`
3. Click on attached policies
4. Edit the policy that allows Bedrock access
5. Add Llama models to the Resource list:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude*",
        "arn:aws:bedrock:*::foundation-model/meta.llama*"
      ]
    }
  ]
}
```

### Option 2: Use AWS Managed Policy

Attach the AWS managed policy `AmazonBedrockFullAccess` to your IAM user:

1. Go to IAM Console
2. Find user: `BedrockAPIKey-hbsh`
3. Click "Add permissions" → "Attach policies directly"
4. Search for: `AmazonBedrockFullAccess`
5. Attach it

⚠️  **Note:** This gives full Bedrock access. Use Option 1 for least-privilege.

### Option 3: Create New API Key with Correct Permissions

1. Create a new IAM user or role with Bedrock permissions
2. Grant `bedrock:InvokeModel` for both Claude and Llama:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/*"
      ]
    }
  ]
}
```

3. Generate new API key
4. Update `bedrock_config.py` with new key

## Verification

After fixing permissions, run:

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend
python3 test_llama_boto3.py
```

Should see:
```
✅ SUCCESS!
Generated text: John Doe
```

Then run the full comparison:
```bash
./run_loan30_comparison.sh
```

## Alternative: Use Claude-Only Analysis

If you can't fix permissions immediately, you can still analyze Claude's results:

```bash
# Claude extracted perfectly - see the results:
cat ../outputs/model_comparison/loan_1579510_v2/claude_opus_4.5_*.json
```

Key findings from Claude:
- ✅ Correctly extracted "Other Obligations" table
- ✅ Math validates perfectly
- ✅ All critical fields accurate
- ✅ No table alignment errors

Once Llama permissions are fixed, re-run the comparison to see how Llama compares!

