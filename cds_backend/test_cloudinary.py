#!/usr/bin/env python3
"""Test Cloudinary configuration and upload"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

print("=" * 60)
print("CLOUDINARY CONFIGURATION TEST")
print("=" * 60)

# Check if cloudinary is installed
try:
    import cloudinary
    import cloudinary.uploader
    print("✓ Cloudinary module installed")
except ImportError as e:
    print(f"✗ Cloudinary module not found: {e}")
    sys.exit(1)

# Check environment variables
cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
api_key = os.getenv("CLOUDINARY_API_KEY")
api_secret = os.getenv("CLOUDINARY_API_SECRET")

print(f"\nEnvironment Variables:")
print(f"  CLOUDINARY_CLOUD_NAME: {cloud_name if cloud_name else '❌ NOT SET'}")
print(f"  CLOUDINARY_API_KEY: {api_key[:10] + '...' if api_key else '❌ NOT SET'}")
print(f"  CLOUDINARY_API_SECRET: {api_secret[:10] + '...' if api_secret else '❌ NOT SET'}")

if not cloud_name or not api_key or not api_secret:
    print("\n❌ ERROR: Missing Cloudinary credentials in environment variables!")
    print("\nAdd these to your .env file:")
    print("CLOUDINARY_CLOUD_NAME=your_cloud_name")
    print("CLOUDINARY_API_KEY=your_api_key")
    print("CLOUDINARY_API_SECRET=your_api_secret")
    sys.exit(1)

# Configure cloudinary
cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret,
    secure=True
)

print(f"\n✓ Cloudinary configured")

# Note: Skipping API ping - focus on upload test

# Test upload with a simple test image
print(f"\nTesting image upload...")

# Create a simple test image using PIL if available, otherwise use a valid PNG
test_image_path = os.path.join(basedir, "test_image.png")
try:
    try:
        from PIL import Image as PILImage
        # Create a simple red image
        img = PILImage.new('RGB', (10, 10), color='red')
        img.save(test_image_path)
        print(f"✓ Test image created with PIL: {test_image_path}")
    except ImportError:
        # Fallback: use a valid PNG hex data
        png_data = bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000a0000000a"
            "0802000000027de8cf0000001849444154789cc360f8cfc060"
            "000300000c0002b29e6e080000000049454e44ae426082"
        )
        with open(test_image_path, 'wb') as f:
            f.write(png_data)
        print(f"✓ Test image created: {test_image_path}")
except Exception as e:
    print(f"✗ Failed to create test image: {e}")
    sys.exit(1)

# Try uploading
try:
    with open(test_image_path, 'rb') as f:
        result = cloudinary.uploader.upload(
            f,
            folder="test_gallery",
            resource_type="image",
            public_id="test_upload_" + str(os.getpid())
        )
    print(f"✓ Upload successful!")
    print(f"  URL: {result.get('secure_url')}")
    print(f"  Public ID: {result.get('public_id')}")
    
    # Clean up test image
    try:
        cloudinary.uploader.destroy(result.get('public_id'))
        print(f"✓ Test image cleaned up")
    except:
        pass
        
except Exception as e:
    print(f"✗ Upload failed: {e}")
    sys.exit(1)
finally:
    # Clean up local test file
    try:
        os.remove(test_image_path)
    except:
        pass

print("\n" + "=" * 60)
print("✓ ALL TESTS PASSED - Cloudinary is working correctly!")
print("=" * 60)
