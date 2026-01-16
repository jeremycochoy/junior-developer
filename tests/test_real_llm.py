"""
Test pairwise judge with real LLM (requires API keys in .env)
"""

import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("❌ ERROR: No API key found!")
    print("Please set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env file")
    exit(1)

print("✅ API key found")

from junior_dev import BTMMScoringEngine, PairwiseJudge

def test_real_llm_comparison():
    print("\n" + "="*70)
    print("REAL LLM TEST - Pairwise Judge")
    print("="*70)
    
    if os.getenv("ANTHROPIC_API_KEY"):
        model = "claude-3-5-sonnet-20241022"
        print(f"Using Anthropic: {model}")
    else:
        model = "gpt-4o-mini"
        print(f"Using OpenAI: {model}")
    
    print("\n1. Initializing Pairwise Judge with real LLM...")
    judge = PairwiseJudge(
        llm_model=model,
        temperature=0.0,
        max_tokens=1000
    )
    
    if judge.llm is None:
        print("❌ LLM client not initialized - ShinkaEvolve may not be installed")
        return
    
    print(f"   ✅ LLM client initialized: {judge.llm}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = BTMMScoringEngine(db_path=str(db_path))
        
        task_spec = """
        Refactor this Python code to improve maintainability:
        
        Original code (visualization in training class):
        class Trainer:
            def train(self):
                self.model.fit()
                self.visualize_loss()
                self.visualize_accuracy()
            
            def visualize_loss(self):
                plt.plot(self.losses)
                plt.savefig('loss.png')
            
            def visualize_accuracy(self):
                plt.plot(self.accuracies)
                plt.savefig('accuracy.png')
                
        Goal: Move visualization to separate module.
        """
        
        candidate_a = """
        ## Refactoring Plan
        
        1. Create new file `visualization.py`
        2. Move `visualize_loss` and `visualize_accuracy` to a `Visualizer` class
        3. Update `Trainer` to use the new `Visualizer` class
        4. Add proper imports
        
        Result:
        # visualization.py
        class Visualizer:
            def __init__(self, trainer):
                self.trainer = trainer
            
            def plot_loss(self):
                plt.plot(self.trainer.losses)
                plt.savefig('loss.png')
            
            def plot_accuracy(self):
                plt.plot(self.trainer.accuracies)
                plt.savefig('accuracy.png')
        
        # trainer.py
        class Trainer:
            def __init__(self):
                self.visualizer = Visualizer(self)
            
            def train(self):
                self.model.fit()
                self.visualizer.plot_loss()
                self.visualizer.plot_accuracy()
                """
        
        candidate_b = """
        ## Refactoring Plan
        
        Move visualization functions to a utility module with static methods.
        
        Result:
        
        # vis_utils.py
        import matplotlib.pyplot as plt
        
        def plot_metric(values, filename, title):
            plt.figure()
            plt.plot(values)
            plt.title(title)
            plt.savefig(filename)
            plt.close()
        
        # trainer.py
        from vis_utils import plot_metric
        
        class Trainer:
            def train(self):
                self.model.fit()
                plot_metric(self.losses, 'loss.png', 'Training Loss')
                plot_metric(self.accuracies, 'accuracy.png', 'Accuracy')
                """
        
        print("\n2. Running comparison with real LLM...")
        print(f"   Task: Refactoring visualization code")
        print(f"   Candidate A: Class-based Visualizer")
        print(f"   Candidate B: Utility functions")
        
        result = judge.compare_detailed(
            task_spec=task_spec,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            context=None
        )
        
        print(f"\n3. LLM Response:")
        print(f"   Winner: {'Candidate A' if result.winner == 'a' else 'Candidate B' if result.winner == 'b' else 'Tie'}")
        print(f"   \n   Reasoning:\n   {result.reasoning[:500]}...")
        
        score_a, score_b = engine.record_comparison(
            candidate_a="class_based_visualizer",
            candidate_b="utility_functions",
            winner=result.winner,
            reasoning=result.reasoning
        )
        
        print(f"\n4. BT-MM Scores Updated:")
        print(f"   class_based_visualizer: {score_a:.4f}")
        print(f"   utility_functions: {score_b:.4f}")
        
        stats = judge.get_statistics()
        print(f"\n5. Judge Statistics:")
        print(f"   Total comparisons: {stats['total_comparisons']}")
        print(f"   Total cost: ${stats['total_cost']:.4f}")
        print(f"   Model: {stats['model']}")
        
        engine.close()
        
    print("\n" + "="*70)
    print("✅ REAL LLM TEST PASSED")
    print("="*70)


if __name__ == "__main__":
    test_real_llm_comparison()