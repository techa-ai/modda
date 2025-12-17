"""
VLM Utilities - Centralized Vision Language Model Access

This module provides a unified interface for VLM operations across all scripts.
Currently uses AWS Bedrock (Claude Opus 4.5), but can be easily switched to other providers.

Usage:
    from vlm_utils import VLMClient
    
    client = VLMClient()
    result = client.process_document(pdf_path, prompt)
    result = client.process_images(image_list, prompt)
    result = client.process_text(text, prompt)
"""

import os
import json
import base64
from pathlib import Path
from typing import List, Dict, Optional, Union
from pdf2image import convert_from_path
import io

# Import Bedrock configuration
from bedrock_config import BedrockClient, BEDROCK_API_KEY, DEFAULT_MODEL, BEDROCK_MODELS


class VLMClient:
    """
    Centralized VLM client for document processing.
    
    Provides consistent interface regardless of underlying provider.
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ):
        """
        Initialize VLM client.
        
        Args:
            model: Model name (default: claude-opus-4-5)
            api_key: Optional API key override
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
        """
        self.model = model
        self.api_key = api_key or BEDROCK_API_KEY
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = BedrockClient(api_key=self.api_key, model=self.model)
    
    def process_document(
        self,
        pdf_path: Union[str, Path],
        prompt: str,
        dpi: int = 150,
        max_pages: Optional[int] = None,
        return_json: bool = True
    ) -> Optional[Dict]:
        """
        Process a PDF document with VLM.
        
        Args:
            pdf_path: Path to PDF file
            prompt: Text prompt for analysis
            dpi: DPI for PDF rendering (default: 150)
            max_pages: Maximum pages to process (None = all)
            return_json: Parse response as JSON (default: True)
        
        Returns:
            Parsed JSON dict or raw text response
        """
        try:
            # Convert PDF to images
            images = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                fmt='jpeg',
                last_page=max_pages
            )
            
            # Convert to base64
            base64_images = []
            for img in images:
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=85)
                img_b64 = base64.b64encode(buffered.getvalue()).decode()
                base64_images.append(img_b64)
            
            # Process with VLM
            return self.process_images(base64_images, prompt, return_json=return_json)
            
        except Exception as e:
            print(f"Error processing document: {e}")
            return None
    
    def process_images(
        self,
        images: List[str],
        prompt: str,
        return_json: bool = True
    ) -> Optional[Union[Dict, str]]:
        """
        Process a list of base64-encoded images with VLM.
        
        Args:
            images: List of base64-encoded image strings
            prompt: Text prompt for analysis
            return_json: Parse response as JSON (default: True)
        
        Returns:
            Parsed JSON dict or raw text response
        """
        try:
            # Prepare content
            content_parts = [{"type": "text", "text": prompt}]
            
            # Add images
            for img_b64 in images:
                content_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_b64
                    }
                })
            
            # Build messages
            messages = [{
                "role": "user",
                "content": content_parts
            }]
            
            # Call VLM
            result = self.client.invoke_model(
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # Parse response
            content = result['content']
            
            if return_json:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    print("Warning: Failed to parse JSON response, returning raw text")
                    return content
            else:
                return content
                
        except Exception as e:
            print(f"Error processing images: {e}")
            return None
    
    def process_text(
        self,
        text: str,
        prompt: str,
        return_json: bool = True
    ) -> Optional[Union[Dict, str]]:
        """
        Process text content with VLM (no images).
        
        Args:
            text: Text content to analyze
            prompt: Analysis prompt
            return_json: Parse response as JSON (default: True)
        
        Returns:
            Parsed JSON dict or raw text response
        """
        try:
            # Combine prompt and text
            full_prompt = f"{prompt}\n\nContent to analyze:\n{text}"
            
            messages = [{
                "role": "user",
                "content": full_prompt
            }]
            
            # Call VLM
            result = self.client.invoke_model(
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # Parse response
            content = result['content']
            
            if return_json:
                try:
                    clean_content = content
                    if "```json" in content:
                        clean_content = content.split("```json")[1].split("```")[0]
                    elif "```" in content:
                        clean_content = content.split("```")[1].split("```")[0]
                    
                    return json.loads(clean_content.strip())
                except json.JSONDecodeError:
                    # Fallback: Find first { and last }
                    try:
                        start = content.find("{")
                        end = content.rfind("}") + 1
                        if start != -1 and end != -1:
                           json_str = content[start:end]
                           return json.loads(json_str)
                    except Exception as e:
                        print(f"Fallback JSON parse failed: {e}")
                        pass
                        
                    print(f"Warning: Failed to parse JSON response. Content first 200 chars: {content[:200]}")
                    return content
            else:
                return content
                
        except Exception as e:
            print(f"Error processing text: {e}")
            return None
    
    def get_model_info(self) -> Dict:
        """Get current model configuration"""
        return {
            'model': self.model,
            'model_id': BEDROCK_MODELS.get(self.model, 'unknown'),
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'provider': 'AWS Bedrock'
        }


# Convenience functions for backward compatibility

def call_vlm_with_pdf(
    pdf_path: Union[str, Path],
    prompt: str,
    model: str = DEFAULT_MODEL,
    dpi: int = 150,
    max_pages: Optional[int] = None
) -> Optional[Dict]:
    """
    Simple function to process PDF with VLM.
    
    Args:
        pdf_path: Path to PDF
        prompt: Analysis prompt
        model: Model to use
        dpi: Rendering DPI
        max_pages: Max pages to process
    
    Returns:
        Parsed JSON response
    """
    client = VLMClient(model=model)
    return client.process_document(pdf_path, prompt, dpi=dpi, max_pages=max_pages)


def call_vlm_with_images(
    images: List[str],
    prompt: str,
    model: str = DEFAULT_MODEL
) -> Optional[Dict]:
    """
    Simple function to process images with VLM.
    
    Args:
        images: List of base64 image strings
        prompt: Analysis prompt
        model: Model to use
    
    Returns:
        Parsed JSON response
    """
    client = VLMClient(model=model)
    return client.process_images(images, prompt)


def call_vlm_with_text(
    text: str,
    prompt: str,
    model: str = DEFAULT_MODEL
) -> Optional[Dict]:
    """
    Simple function to process text with VLM.
    
    Args:
        text: Text content
        prompt: Analysis prompt
        model: Model to use
    
    Returns:
        Parsed JSON response
    """
    client = VLMClient(model=model)
    return client.process_text(text, prompt)


# Example usage
if __name__ == "__main__":
    print("VLM Utilities - Test")
    print("=" * 60)
    
    client = VLMClient()
    info = client.get_model_info()
    
    print(f"Provider: {info['provider']}")
    print(f"Model: {info['model']}")
    print(f"Model ID: {info['model_id']}")
    print(f"Temperature: {info['temperature']}")
    print(f"Max Tokens: {info['max_tokens']}")
    print()
    print("✓ VLM client initialized successfully")
