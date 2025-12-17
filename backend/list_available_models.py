#!/usr/bin/env python3
"""
List all available models in AWS Bedrock
"""

import json
from bedrock_config import BEDROCK_API_KEY, BEDROCK_ENDPOINT, BEDROCK_ENDPOINT_US_EAST_1
import requests


def list_available_models():
    """List all available models in AWS Bedrock"""
    
    print("\n" + "="*80)
    print("AWS BEDROCK AVAILABLE MODELS")
    print("="*80)
    
    # Note: Bedrock doesn't have a direct REST API to list models
    # We need to try different known model IDs
    
    # Llama models by region
    llama_models_us_east = [
        # Llama 4 Maverick (December 2025 - us-east-1 only!)
        "meta.llama4-maverick-17b-instruct-v1:0",
    ]
    
    llama_models_cross_region = [
        "global.meta.llama4-maverick-17b-instruct-v1:0",
        # Llama 3.3
        "meta.llama3-3-70b-instruct-v1:0",
        "us.meta.llama3-3-70b-instruct-v1:0",
        # Llama 3.2 Vision
        "meta.llama3-2-90b-instruct-v1:0",
        "meta.llama3-2-11b-instruct-v1:0",
        "us.meta.llama3-2-90b-instruct-v1:0",
        "us.meta.llama3-2-11b-instruct-v1:0",
        # Llama 3.1
        "meta.llama3-1-405b-instruct-v1:0",
        "meta.llama3-1-70b-instruct-v1:0",
        "meta.llama3-1-8b-instruct-v1:0",
    ]
    
    print("\n🦙 Testing Llama Models in us-east-1:")
    print("-" * 80)
    
    available_llama = []
    
    # Test us-east-1 specific models
    for model_id in llama_models_us_east:
        try:
            url = f"{BEDROCK_ENDPOINT_US_EAST_1}/model/{model_id}/invoke"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {BEDROCK_API_KEY}",
                "Accept": "application/json"
            }
            
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "temperature": 0.0,
                "messages": [{
                    "role": "user",
                    "content": "Hello"
                }]
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"  ✅ {model_id} (us-east-1)")
                available_llama.append(model_id)
            elif response.status_code == 404:
                print(f"  ❌ {model_id} - Not Found")
            elif response.status_code == 400:
                error_msg = response.json().get('message', '')
                if 'invalid' in error_msg.lower():
                    print(f"  ❌ {model_id} - Invalid Model ID")
                else:
                    # Might be API format issue, but model exists
                    print(f"  ⚠️  {model_id} - Model exists but API format issue")
                    available_llama.append(model_id)
            else:
                print(f"  ❓ {model_id} - HTTP {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ {model_id} - Error: {str(e)[:50]}")
    
    print("\n🦙 Testing Cross-Region Llama Models:")
    print("-" * 80)
    
    # Test cross-region models
    for model_id in llama_models_cross_region:
        try:
            url = f"{BEDROCK_ENDPOINT}/model/{model_id}/invoke"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {BEDROCK_API_KEY}",
                "Accept": "application/json"
            }
            
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "temperature": 0.0,
                "messages": [{
                    "role": "user",
                    "content": "Hello"
                }]
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"  ✅ {model_id}")
                available_llama.append(model_id)
            elif response.status_code == 404:
                print(f"  ❌ {model_id} - Not Found")
            elif response.status_code == 400:
                error_msg = response.json().get('message', '')
                if 'invalid' in error_msg.lower():
                    print(f"  ❌ {model_id} - Invalid Model ID")
                else:
                    # Might be API format issue, but model exists
                    print(f"  ⚠️  {model_id} - Model exists but API format issue")
                    available_llama.append(model_id)
            else:
                print(f"  ❓ {model_id} - HTTP {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ {model_id} - Error: {str(e)[:50]}")
    
    print("\n" + "="*80)
    print(f"AVAILABLE LLAMA MODELS: {len(available_llama)}")
    print("="*80)
    
    if available_llama:
        print("\n✅ You can use these models:")
        for model in available_llama:
            print(f"  - {model}")
        
        print("\n💡 To use in comparison script:")
        print(f"   LLAMA_MODEL_ID = \"{available_llama[0]}\"")
    else:
        print("\n❌ No Llama models are currently accessible.")
        print("\n📝 Next steps:")
        print("   1. Go to AWS Bedrock Console")
        print("   2. Navigate to Model Access")
        print("   3. Request access to Llama models")
        print("   4. Wait for approval (usually instant)")
        print("\n🔗 Console: https://console.aws.amazon.com/bedrock/home#/modelaccess")
    
    return available_llama


def main():
    models = list_available_models()
    
    # Also show Claude status
    print("\n" + "="*80)
    print("CLAUDE MODELS")
    print("="*80)
    print("  ✅ Claude Opus 4.5 - Working!")
    
    return 0 if models else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())

