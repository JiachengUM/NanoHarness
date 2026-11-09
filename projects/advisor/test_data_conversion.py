import json

from cabin_advisor.worker.comfort_advisor_worker import ComfortAdvisorWorker, SchemaConfig

from nanoai.utils.logger import get_logger

logger = get_logger(__name__)


class User:
    """Example User class for testing"""
    pass

def compare_dicts_simple(dict1, dict2, path=""):
    """Simple dictionary comparison function that returns differences"""
    differences = {}
    
    # Get all keys from both dictionaries
    all_keys = set(dict1.keys()) | set(dict2.keys())
    
    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        
        # Check if key is in both dictionaries
        if key not in dict1:
            differences[current_path] = {"status": "added", "value": dict2[key]}
        elif key not in dict2:
            differences[current_path] = {"status": "removed", "value": dict1[key]}
        else:
            value1 = dict1[key]
            value2 = dict2[key]
            
            # If both values are dictionaries, recursively compare
            if isinstance(value1, dict) and isinstance(value2, dict):
                nested_diffs = compare_dicts_simple(value1, value2, current_path)
                if nested_diffs:
                    differences.update(nested_diffs)
            # If both values are lists, compare their elements
            elif isinstance(value1, list) and isinstance(value2, list):
                if len(value1) != len(value2):
                    differences[current_path] = {"status": "changed", "old_value": value1, "new_value": value2}
                else:
                    # Compare list elements
                    for i, (item1, item2) in enumerate(zip(value1, value2)):
                        item_path = f"{current_path}[{i}]"
                        if isinstance(item1, dict) and isinstance(item2, dict):
                            nested_diffs = compare_dicts_simple(item1, item2, item_path)
                            if nested_diffs:
                                differences.update(nested_diffs)
                        elif item1 != item2:
                            differences[item_path] = {"status": "changed", "old_value": item1, "new_value": item2}
            # Compare simple values
            elif value1 != value2:
                differences[current_path] = {"status": "changed", "old_value": value1, "new_value": value2}
    
    return differences

def compare_dicts(dict1, dict2, step_name):
    """Compare two dictionaries and print differences"""
    logger.info(f"\n=== {step_name} - Data Comparison ===")
    diff = compare_dicts_simple(dict1, dict2)
    
    if not diff:
        logger.info("✅ No differences detected")
        return False
    
    logger.info("🔍 Differences found:")
    
    # Group differences by type
    added = {k: v for k, v in diff.items() if v["status"] == "added"}
    removed = {k: v for k, v in diff.items() if v["status"] == "removed"}
    changed = {k: v for k, v in diff.items() if v["status"] == "changed"}
    
    # Check for added keys
    if added:
        logger.info("\n📝 Added keys:")
        for key, info in added.items():
            logger.info(f"   - {key}: {info['value']}")
    
    # Check for removed keys
    if removed:
        logger.info("\n🗑️ Removed keys:")
        for key, info in removed.items():
            logger.info(f"   - {key}: {info['value']}")
    
    # Check for changed values
    if changed:
        logger.info("\n🔄 Changed values:")
        for key, info in changed.items():
            logger.info(f"   - {key}: {info['old_value']} → {info['new_value']}")
    
    return True

def count_keys(data, prefix=""):
    """Count total number of keys in nested dictionary"""
    count = 0
    if isinstance(data, dict):
        for key, value in data.items():
            count += 1
            count += count_keys(value, f"{prefix}{key}.")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            count += count_keys(item, f"{prefix}[{i}].")
    return count
def test_data_conversion():
    """Test data conversion process and check for data loss"""
    # Configuration
    model_path = ""
    # model_path = "F:/Download/qwen3-1.7B"
    # model_path = "/Users/chris-macbookair/Downloads/qwen3/qwen3-0.6B"
    json_path = "data/user_complete_data.json"
    try:
        # Initialize worker
        logger.info("🔧 Initializing ComfortAdvisorWorker...")
        schema_config = SchemaConfig(
            include_type=False,
            include_defaults=False,
            include_constraints=True,
            include_required=True,
            include_nested=True,
            include_format=True,
            include_description=True
        )
        worker = ComfortAdvisorWorker(model=model_path, schema_config=schema_config)
        
        # Step 1: Read JSON file
        logger.info("\n📖 Step 1: Reading JSON file")
        filtered_json = worker.parser.read_json(path=json_path)
        logger.info(f"   Data type: {type(filtered_json)}")
        logger.info(f"   Total keys: {count_keys(filtered_json)}")
        logger.info(f"   Sample: {json.dumps(filtered_json, ensure_ascii=False, indent=2)[:300]}...")
        
        # Store original data for comparison
        original_data = filtered_json.copy()
        logger.info("\n🔤 Step 1: Converting JSON to instance")
        instance = worker.json_to_instance(filtered_json, name="user_complete_data")
        
        # Step 2: Convert JSON to prompt
        logger.info("\n🔤 Step 2: Converting INSTANCE to prompt")
        prompt = worker.instance_to_prompt(instance)
        logger.info(f"   Prompt type: {type(prompt)}")
        logger.info(f"   Prompt length: {len(prompt)}")
        logger.info(f"   Prompt sample: {prompt[:300]}...")
        
        # Step 3: Convert prompt to JSON
        logger.info("\n📋 Step 3: Converting PROMPT to JSON")
        json_content = worker.prompt_to_json(prompt)
        logger.info(f"   Data type: {type(json_content)}")
        logger.info(f"   Total keys: {count_keys(json_content)}")
        
        # Check if JSON content is empty (which might happen if FastAPI is not accessible)
        if not json_content:
            logger.warning("   ⚠️ Warning: JSON content is empty. This might be because the FastAPI service is not accessible.")
            logger.warning("   ⚠️ Skipping comparison for this step.")
            # Use original data for the next step to avoid errors
            json_content = original_data.copy()
        else:
            logger.info(f"   Sample: {json.dumps(json_content, ensure_ascii=False, indent=2)[:300]}...")
            # Compare original vs after prompt-to-json conversion
            compare_dicts(original_data, json_content, "JSON → Prompt → JSON")
        
        # Step 4: Convert JSON to Pydantic instance
        logger.info("\n🏗️ Step 4: Converting JSON to Pydantic instance")
        try:
            pydantic_df = worker.json_to_instance(json_content, User.__name__)
            logger.info(f"   Instance type: {type(pydantic_df)}")
            logger.info(f"   Instance: {pydantic_df}")
            
            # Convert back to dict for comparison
            pydantic_dict = pydantic_df.model_dump()
            logger.info(f"   Total keys in Pydantic dict: {count_keys(pydantic_dict)}")
            
            # Compare JSON content vs Pydantic dict
            compare_dicts(json_content, pydantic_dict, "JSON → Pydantic Instance")
            
            # Final comparison: Original vs Final Pydantic dict
            compare_dicts(original_data, pydantic_dict, "Original → Final Pydantic")
            
        except Exception as e:
            logger.error(f"   ❌ Error converting to Pydantic instance: {e}")
            import traceback
            traceback.print_exc()
    
    except Exception as e:
        logger.error(f"❌ Error during test execution: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n=== Test Summary ===")
    logger.info("📊 Data Flow:")
    logger.info("   1. Original JSON → Read by worker.parser.read_json()")
    logger.info("   2. JSON → worker.json_to_prompt() → Prompt")
    logger.info("   3. Prompt → worker.prompt_to_json() → Generated JSON")
    logger.info("   4. Generated JSON → worker.json_to_instance() → Pydantic Instance")
    logger.info("\n💡 Use the comparison results above to identify any data loss or changes during conversion.")

if __name__ == "__main__":
    test_data_conversion()