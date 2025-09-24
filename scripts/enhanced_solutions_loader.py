"""
Enhanced Solutions Loader Script
Loads solutions from ALL JSON files in the solutions directory
Provides comprehensive mapping of question IDs to correct answers and explanations
"""

import os
import json
import sys
from typing import Dict, Any, List, Tuple

def load_comprehensive_solutions() -> Dict[str, Dict[str, Any]]:
    """
    Load solutions from all available solution files and create a comprehensive mapping.
    
    Returns:
        Dict mapping question IDs to {'correct_answer': str, 'explanation': str, 'source': str}
    """
    solutions_map = {}
    
    # Get the solutions directory path
    solutions_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'solutions')
    
    # Get all JSON files in solutions directory
    json_files = [f for f in os.listdir(solutions_dir) if f.endswith('.json')]
    
    print(f"🔍 Found {len(json_files)} JSON files in solutions directory")
    
    stats = {'total_files': len(json_files), 'processed_files': 0, 'solutions_extracted': 0}
    
    for filename in sorted(json_files):
        file_path = os.path.join(solutions_dir, filename)
        try:
            file_solutions = extract_solutions_from_file(file_path, filename)
            
            # Merge solutions, preferring more complete ones
            merged_count = 0
            for qid, solution in file_solutions.items():
                if qid not in solutions_map:
                    solutions_map[qid] = solution
                    merged_count += 1
                else:
                    # Merge/update existing solution with new data
                    existing = solutions_map[qid]
                    updated = False
                    
                    # Prefer non-empty explanations
                    if not existing.get('explanation') and solution.get('explanation'):
                        existing['explanation'] = solution['explanation']
                        updated = True
                    
                    # Prefer non-empty answers
                    if not existing.get('correct_answer') and solution.get('correct_answer'):
                        existing['correct_answer'] = solution['correct_answer']
                        updated = True
                    
                    # Update source to show multiple sources
                    if updated and solution.get('source') != existing.get('source'):
                        existing['source'] = f"{existing.get('source', '')}, {solution.get('source', '')}"
                        merged_count += 1
            
            print(f"  ✅ {filename}: {len(file_solutions)} solutions extracted, {merged_count} new/updated")
            stats['processed_files'] += 1
            stats['solutions_extracted'] += len(file_solutions)
            
        except Exception as e:
            print(f"  ⚠️  Error processing {filename}: {e}")
    
    # Calculate quality metrics
    with_answers = sum(1 for s in solutions_map.values() if s.get('correct_answer'))
    with_explanations = sum(1 for s in solutions_map.values() if s.get('explanation'))
    
    print(f"\n📊 COMPREHENSIVE SOLUTIONS SUMMARY:")
    print(f"   Files processed: {stats['processed_files']}/{stats['total_files']}")
    print(f"   Total solutions found: {stats['solutions_extracted']:,}")
    print(f"   Unique question IDs: {len(solutions_map):,}")
    print(f"   Solutions with answers: {with_answers:,} ({with_answers/len(solutions_map)*100:.1f}%)")
    print(f"   Solutions with explanations: {with_explanations:,} ({with_explanations/len(solutions_map)*100:.1f}%)")
    
    return solutions_map

def extract_solutions_from_file(file_path: str, filename: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract solutions from a single JSON file based on its structure.
    
    Args:
        file_path: Path to the JSON file
        filename: Name of the file for logging
        
    Returns:
        Dict mapping question IDs to solution data
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    solutions = {}
    
    # Check if it's the comprehensive_solutions format (direct mapping)
    if isinstance(data, dict) and len(data) > 100 and all(isinstance(k, str) and len(k) > 20 for k in list(data.keys())[:5]):
        # Direct mapping format: {qid: {correct_answer, explanation, source}}
        return data
    
    # Check for result.data.sec_questions format
    if 'result' in data and isinstance(data['result'], dict):
        result_data = data['result']
        if 'data' in result_data and isinstance(result_data['data'], dict):
            sec_questions = result_data['data'].get('sec_questions', [])
            if isinstance(sec_questions, list):
                solutions = extract_from_sec_questions(sec_questions, filename)
    
    return solutions

def extract_from_sec_questions(sec_questions: list, filename: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract solutions from sec_questions list format.
    
    Args:
        sec_questions: List of question data arrays
        filename: Source filename for reference
        
    Returns:
        Dict mapping question IDs to solution data
    """
    solutions = {}
    
    for q in sec_questions:
        if isinstance(q, list) and len(q) > 12:
            # Try position 12 first (most common QID location)
            qid = q[12] if q[12] and isinstance(q[12], str) and len(q[12]) > 20 else None
            
            # Fallback to position 7 (used in some Biology files)
            if not qid and len(q) > 7:
                qid = q[7] if q[7] and isinstance(q[7], str) and len(q[7]) > 20 else None
            
            if qid:
                # Extract correct answer (position 4 contains answer indices)
                correct_answer = None
                if len(q) > 4 and isinstance(q[4], list) and q[4]:
                    # Convert answer index to letter (0->A, 1->B, etc.)
                    answer_index = q[4][0] if isinstance(q[4][0], int) else None
                    if answer_index is not None and 0 <= answer_index <= 25:
                        correct_answer = chr(ord('A') + answer_index)
                
                # Extract explanation (position 6)
                explanation = q[6] if len(q) > 6 and q[6] else None
                
                # Only include if we have at least an answer or explanation
                if correct_answer or explanation:
                    solutions[qid] = {
                        'correct_answer': correct_answer,
                        'explanation': clean_explanation(explanation) if explanation else None,
                        'source': filename
                    }
    
    return solutions

def clean_explanation(explanation: str) -> str:
    """
    Clean explanation text by removing excessive HTML and formatting for readability.
    
    Args:
        explanation: Raw explanation text
        
    Returns:
        Cleaned explanation text
    """
    if not explanation:
        return None
    
    try:
        import re
        
        # Keep mathematical notation but clean HTML
        explanation = str(explanation)
        
        # Replace HTML entities
        explanation = explanation.replace('&nbsp;', ' ')
        explanation = explanation.replace('&lt;', '<')
        explanation = explanation.replace('&gt;', '>')
        explanation = explanation.replace('&amp;', '&')
        explanation = explanation.replace('&quot;', '"')
        
        # Remove HTML tags but preserve content and mathematical notation
        # Keep \( \) and \[ \] for LaTeX math
        explanation = re.sub(r'<(?!\/?(p|br|span))[^>]*>', '', explanation)
        
        # Clean up excessive whitespace
        explanation = re.sub(r'\s+', ' ', explanation)
        explanation = explanation.strip()
        
        return explanation if explanation else None
        
    except Exception as e:
        print(f"Warning: Error cleaning explanation: {e}")
        return str(explanation) if explanation else None

if __name__ == '__main__':
    # Test the loader
    print("🧪 Testing Enhanced Solutions Loader")
    print("=" * 50)
    
    solutions = load_comprehensive_solutions()
    
    print("\n🔍 Sample solutions:")
    sample_count = 0
    for qid, solution in solutions.items():
        if sample_count >= 3:
            break
        print(f"\nQID: {qid}")
        print(f"Answer: {solution.get('correct_answer', 'N/A')}")
        print(f"Explanation: {solution.get('explanation', 'N/A')[:100]}...")
        print(f"Source: {solution.get('source', 'N/A')}")
        sample_count += 1
