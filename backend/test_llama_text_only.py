#!/usr/bin/env python3
"""Test Llama 4 with text-only (no images) to isolate the issue"""

import requests
import json
from bedrock_config import BEDROCK_API_KEY

def test_llama_text_only():
    """Test Llama with simple text prompt"""
    
    model_id = "arn:aws:bedrock:us-east-1::foundation-model/meta.llama4-maverick-17b-instruct-v1:0"
    url = f"https://bedrock-runtime.us-east-1.amazonaws.com/model/{model_id}/invoke"
    
    # Format prompt with Llama's special tokens
    prompt = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>
Extract the borrower name from this 1008 form text: "Borrower: John Doe, SSN: 123-45-6789"
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
    
    body = {
        "prompt": prompt,
        "max_gen_len": 100,
        "temperature": 0.0
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BEDROCK_API_KEY}",
        "Accept": "application/json"
    }
    
    print("Testing Llama 4 with TEXT ONLY...")
    print(f"Model: {model_id}")
    print(f"URL: {url}\n")
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ SUCCESS with text-only!")
            print(f"Response: {json.dumps(result, indent=2)}")
            if 'generation' in result:
                print(f"\nGenerated text: {result['generation']}")
            return True
        else:
            print(f"\n❌ FAILED")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_llama_with_images():
    """Test Llama with images to see if multimodal works"""
    
    model_id = "arn:aws:bedrock:us-east-1::foundation-model/meta.llama4-maverick-17b-instruct-v1:0"
    url = f"https://bedrock-runtime.us-east-1.amazonaws.com/model/{model_id}/invoke"
    
    # Minimal test image (1x1 pixel white JPEG in base64)
    test_image = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA/9k="
    
    prompt = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>
What do you see in this image?
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
    
    body = {
        "prompt": prompt,
        "max_gen_len": 100,
        "temperature": 0.0,
        "images": [test_image]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BEDROCK_API_KEY}",
        "Accept": "application/json"
    }
    
    print("\n" + "="*80)
    print("Testing Llama 4 with IMAGE...")
    print(f"Model: {model_id}")
    print(f"URL: {url}\n")
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ SUCCESS with images!")
            print(f"Response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"\n❌ FAILED")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    print("="*80)
    print("LLAMA 4 MAVERICK - TEXT VS MULTIMODAL TEST")
    print("="*80)
    
    text_works = test_llama_text_only()
    images_work = test_llama_with_images()
    
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"Text-only: {'✅ WORKS' if text_works else '❌ FAILED'}")
    print(f"With images: {'✅ WORKS' if images_work else '❌ FAILED'}")
    
    if text_works and not images_work:
        print("\n⚠️  Llama 4 Maverick works with text but not images")
        print("Recommendation: Use OCR to extract text from PDFs first")




