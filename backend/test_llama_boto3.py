#!/usr/bin/env python3
"""Test Llama 4 using boto3 SDK instead of REST API"""

import boto3
import json

def test_llama_with_boto3():
    """Test Llama 4 using boto3 (official AWS SDK)"""
    
    print("="*80)
    print("TESTING LLAMA 4 WITH BOTO3 SDK")
    print("="*80)
    
    # Create Bedrock Runtime client
    client = boto3.client(
        service_name='bedrock-runtime',
        region_name='us-east-1'
    )
    
    model_id = "meta.llama4-maverick-17b-instruct-v1:0"
    
    # Format prompt with Llama's special tokens
    prompt = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>
Extract the borrower name from this text: "Borrower: John Doe"
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
    
    # Request body
    body = json.dumps({
        "prompt": prompt,
        "max_gen_len": 100,
        "temperature": 0.0
    })
    
    print(f"Model ID: {model_id}")
    print(f"Region: us-east-1")
    print(f"Using boto3 SDK...\n")
    
    try:
        # Invoke model
        response = client.invoke_model(
            modelId=model_id,
            body=body
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        
        print("✅ SUCCESS!")
        print(f"Response: {json.dumps(response_body, indent=2)}\n")
        
        if 'generation' in response_body:
            print(f"Generated text: {response_body['generation']}")
            return True
        else:
            print(f"⚠️  Unexpected response format")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_llama_with_boto3()
    
    if success:
        print("\n✅ Llama 4 works with boto3!")
        print("Need to update comparison script to use boto3 instead of REST API")
    else:
        print("\n❌ Llama 4 doesn't work with boto3 either")




