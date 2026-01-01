#!/usr/bin/env python3
"""
Direct test of Llama 4 Maverick in us-east-1 region
"""

import requests
import json
from bedrock_config import BEDROCK_API_KEY

def test_llama_direct_us_east():
    """Test Llama 4 Maverick directly in us-east-1"""
    
    print("\n" + "="*80)
    print("LLAMA 4 MAVERICK - DIRECT US-EAST-1 TEST")
    print("="*80)
    
    # Try different model ID formats
    model_variations = [
        ("Direct model ID", "meta.llama4-maverick-17b-instruct-v1:0"),
        ("Cross-region profile (us.)", "us.meta.llama4-maverick-17b-instruct-v1:0"),
        ("Cross-region profile (global.)", "global.meta.llama4-maverick-17b-instruct-v1:0"),
    ]
    
    endpoint_us_east = "https://bedrock-runtime.us-east-1.amazonaws.com"
    
    for label, model_id in model_variations:
        print(f"\n{'='*80}")
        print(f"Testing: {label}")
        print(f"Model ID: {model_id}")
        print(f"Region: us-east-1")
        print(f"{'='*80}")
        
        url = f"{endpoint_us_east}/model/{model_id}/invoke"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BEDROCK_API_KEY}",
            "Accept": "application/json"
        }
        
        # Try with Messages API format (like Claude)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "temperature": 0.0,
            "messages": [{
                "role": "user",
                "content": "Say 'Hello from Llama 4 Maverick!'"
            }]
        }
        
        try:
            print(f"  🔄 Calling {model_id}...")
            print(f"  🌐 Endpoint: {url}")
            
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=30
            )
            
            print(f"  📊 Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"  ✅ SUCCESS!")
                print(f"  📝 Response: {json.dumps(result, indent=2)}")
                
                # Extract text if available
                if 'content' in result and len(result['content']) > 0:
                    print(f"  💬 Text: {result['content'][0].get('text', 'N/A')}")
                elif 'generation' in result:
                    print(f"  💬 Text: {result['generation']}")
                
                return True
            else:
                error_data = response.json() if response.text else {}
                print(f"  ❌ FAILED")
                print(f"  📝 Error: {json.dumps(error_data, indent=2)}")
                
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            import traceback
            traceback.print_exc()
    
    return False

def test_llama_with_inference_profile():
    """Test with full inference profile ARN format"""
    
    print("\n" + "="*80)
    print("TESTING WITH INFERENCE PROFILE FORMATS")
    print("="*80)
    
    # Common inference profile patterns
    profiles = [
        "us.meta.llama4-maverick-17b-instruct-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/meta.llama4-maverick-17b-instruct-v1:0",
    ]
    
    endpoint = "https://bedrock-runtime.us-east-1.amazonaws.com"
    
    for profile in profiles:
        print(f"\n  Testing profile: {profile}")
        
        url = f"{endpoint}/model/{profile}/invoke"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BEDROCK_API_KEY}",
            "Accept": "application/json"
        }
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "temperature": 0.0,
            "messages": [{
                "role": "user",
                "content": "Hello"
            }]
        }
        
        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)
            print(f"    Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"    ✅ SUCCESS with {profile}")
                result = response.json()
                if 'content' in result:
                    print(f"    Response: {result['content'][0].get('text', '')[:100]}")
                return True
            else:
                print(f"    Error: {response.json().get('message', 'Unknown')}")
                
        except Exception as e:
            print(f"    Exception: {str(e)[:100]}")
    
    return False

def check_model_access():
    """Check if we have access to Llama models"""
    
    print("\n" + "="*80)
    print("CHECKING MODEL ACCESS STATUS")
    print("="*80)
    
    print("""
To enable Llama 4 Maverick access:

1. Go to AWS Bedrock Console:
   https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess

2. Look for "Llama 4 Maverick 17B Instruct"

3. Check the status:
   - "Access granted" ✅ → You're good!
   - "Request access" → Click to enable
   - "Access pending" → Wait a moment

4. After enabling, wait 1-2 minutes for propagation

5. Re-run this test
""")

def main():
    print("\n" + "="*80)
    print("LLAMA 4 MAVERICK - US-EAST-1 CONNECTIVITY TEST")
    print("="*80)
    print("\nThis test will try different ways to access Llama 4 Maverick")
    print("in the us-east-1 region.\n")
    
    # Test 1: Direct model ID variations
    success1 = test_llama_direct_us_east()
    
    # Test 2: Inference profile formats
    success2 = test_llama_with_inference_profile()
    
    # Results
    print("\n" + "="*80)
    print("TEST RESULTS")
    print("="*80)
    
    if success1 or success2:
        print("\n✅ SUCCESS! Llama 4 Maverick is accessible!")
        print("\nYou can now run the full comparison:")
        print("  ./run_loan30_comparison.sh")
        return 0
    else:
        print("\n❌ FAILED - Llama 4 Maverick is not accessible")
        check_model_access()
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())




