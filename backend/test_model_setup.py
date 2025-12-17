#!/usr/bin/env python3
"""
Test script to validate model setup and API access
Tests both Claude Opus 4.5 and Llama 4 Maverick 17B
"""

import sys
from bedrock_config import BedrockClient, BEDROCK_API_KEY, BEDROCK_ENDPOINT, BEDROCK_ENDPOINT_US_EAST_1


def test_claude():
    """Test Claude Opus 4.5 API access"""
    
    print("\n" + "="*60)
    print("Testing Claude Opus 4.5")
    print("="*60)
    
    try:
        client = BedrockClient(model='claude-opus-4-5')
        
        messages = [{
            "role": "user",
            "content": "Respond with exactly: 'Claude Opus 4.5 is working!'"
        }]
        
        print("  🔄 Calling Claude Opus 4.5...")
        result = client.invoke_model(
            messages=messages,
            max_tokens=100,
            temperature=0.0
        )
        
        print(f"  ✅ Success!")
        print(f"  📝 Response: {result['content'][:200]}")
        print(f"  📊 Tokens: {result['usage']}")
        print(f"  🔧 Model: {result['model']}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_llama():
    """Test Llama model API access"""
    
    print("\n" + "="*60)
    print("Testing Llama 4 Maverick 17B")
    print("="*60)
    
    try:
        import requests
        
        # Use Llama 4 Maverick 17B with ARN format
        model_id = "arn:aws:bedrock:us-east-1::foundation-model/meta.llama4-maverick-17b-instruct-v1:0"
        
        # Llama 4 uses its own API format (not Anthropic Messages API)
        body = {
            "prompt": "Respond with exactly: 'Llama is working!'",
            "max_gen_len": 100,
            "temperature": 0.0
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BEDROCK_API_KEY}",
            "Accept": "application/json"
        }
        
        # Llama 4 Maverick must be called from us-east-1
        url = f"{BEDROCK_ENDPOINT_US_EAST_1}/model/{model_id}/invoke"
        
        print(f"  🔄 Calling Llama Model...")
        print(f"  🔧 Model: {model_id[:60]}...")
        print(f"  🌐 Region: us-east-1")
        print(f"  🌐 Endpoint: {url[:80]}...")
        
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"  ✅ Success!")
            # Llama 4 response format
            if 'generation' in result:
                print(f"  📝 Response: {result['generation'][:200]}")
                print(f"  📊 Tokens: prompt={result.get('prompt_token_count', 0)}, generation={result.get('generation_token_count', 0)}")
            # Fallback for other formats
            elif 'content' in result and len(result['content']) > 0:
                print(f"  📝 Response: {result['content'][0]['text'][:200]}")
                print(f"  📊 Tokens: {result.get('usage', {})}")
            return True
        else:
            print(f"  ❌ Error: HTTP {response.status_code}")
            print(f"  📝 Response: {response.text[:500]}")
            return False
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vision_capabilities():
    """Test vision capabilities with a simple image"""
    
    print("\n" + "="*60)
    print("Testing Vision Capabilities")
    print("="*60)
    
    # Create a simple base64-encoded test image (1x1 white pixel JPEG)
    import base64
    
    # Minimal valid JPEG (1x1 white pixel) - properly formatted base64
    test_image_b64 = (
        '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a'
        'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy'
        'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA'
        'AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEB'
        'AQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA/9k='
    )
    
    try:
        client = BedrockClient(model='claude-opus-4-5')
        
        print("  🔄 Testing Claude with image...")
        result = client.invoke_with_image(
            text_prompt="What do you see in this image? Describe it briefly.",
            image_base64=test_image_b64,
            max_tokens=100
        )
        
        print(f"  ✅ Vision test passed!")
        print(f"  📝 Response: {result['content'][:200]}")
        
        return True
        
    except Exception as e:
        print(f"  ⚠️  Vision test failed: {e}")
        print(f"  (This is OK if model doesn't support vision)")
        return False


def check_loan_30_pdf():
    """Check if Loan 30's 1008 PDF exists"""
    
    print("\n" + "="*60)
    print("Checking Loan 30 (1579510) 1008 Form")
    print("="*60)
    
    import os
    
    pdf_path = "../public/loans/loan_1579510/1008___final_0.pdf"
    abs_pdf_path = os.path.abspath(pdf_path)
    
    if os.path.exists(abs_pdf_path):
        file_size = os.path.getsize(abs_pdf_path) / 1024  # KB
        print(f"  ✅ Found: {abs_pdf_path}")
        print(f"  📄 Size: {file_size:.1f} KB")
        return True
    else:
        print(f"  ❌ Not found: {abs_pdf_path}")
        return False


def main():
    """Run all tests"""
    
    print("\n" + "="*60)
    print("MODEL COMPARISON SETUP VALIDATION")
    print("="*60)
    print("\nThis script tests:")
    print("  1. Claude Opus 4.5 API access")
    print("  2. Llama 4 Maverick 17B API access")
    print("  3. Vision capabilities (optional)")
    print("  4. Loan 30 PDF availability")
    
    results = {
        'claude': False,
        'llama': False,
        'vision': False,
        'pdf': False
    }
    
    # Run tests
    results['claude'] = test_claude()
    results['llama'] = test_llama()
    results['vision'] = test_vision_capabilities()
    results['pdf'] = check_loan_30_pdf()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    print(f"  {'✅' if results['claude'] else '❌'} Claude Opus 4.5")
    print(f"  {'✅' if results['llama'] else '❌'} Llama 4 Maverick 17B")
    print(f"  {'✅' if results['vision'] else '⚠️ '} Vision Support (optional)")
    print(f"  {'✅' if results['pdf'] else '❌'} Loan 30 PDF")
    
    all_critical = results['claude'] and results['llama'] and results['pdf']
    
    if all_critical:
        print("\n✅ All critical tests passed! Ready to run comparison.")
        print("\nNext step:")
        print("  ./run_loan30_comparison.sh")
        return 0
    else:
        print("\n❌ Some critical tests failed. Please fix before proceeding.")
        
        if not results['claude']:
            print("\n🔧 Claude Issue:")
            print("   - Check BEDROCK_API_KEY in bedrock_config.py")
            print("   - Verify AWS credentials")
            print("   - Check model access in AWS Bedrock console")
        
        if not results['llama']:
            print("\n🔧 Llama Issue:")
            print("   - Verify model ID: us.meta.llama4-maverick-17b-instruct-v1:0")
            print("   - Request model access in AWS Bedrock console")
            print("   - Go to: Model access → Request access for Llama 4 Maverick")
            print("   - Must use cross-region inference profile (us. prefix)")
            print("   - See LLAMA_MODEL_SETUP.md for alternative models")
        
        if not results['pdf']:
            print("\n🔧 PDF Issue:")
            print("   - Ensure Loan 30 documents are in public/loans/loan_1579510/")
            print("   - Check filename: 1008___final_0.pdf")
        
        return 1


if __name__ == '__main__':
    sys.exit(main())

