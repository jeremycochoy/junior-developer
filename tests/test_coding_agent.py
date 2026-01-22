import tempfile
from pathlib import Path
from junior_dev.coding_agent import CodingAgent, AgentResult

def test_initialization():
    print("\n" + "="*70)
    print("TEST 1: CodingAgent Initialization")
    print("="*70)
    
    agent = CodingAgent(agent_type="mock", timeout=60)
    assert agent.agent_type == "mock"
    assert agent.timeout == 60
    
    print("✓ Initialization test passed\n")


def test_mock_agent():
    print("\n" + "="*70)
    print("TEST 2: Mock Agent Execution")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = CodingAgent(agent_type="mock", timeout=60, working_dir=tmpdir)
        
        result = agent.execute("Test prompt for refactoring")
        
        assert isinstance(result, AgentResult)
        assert result.success == True
        assert result.exit_code == 0
        assert result.changes_made == True
        assert len(result.output) > 0
        assert result.execution_time > 0

        marker = Path(tmpdir) / ".junior_dev_mock_change.txt"
        assert marker.exists()
        assert "Test prompt for refactoring" in marker.read_text()
        
    print("✓ Mock agent test passed\n")


def test_agent_availability():
    print("\n" + "="*70)
    print("TEST 3: Agent Availability Check")
    print("="*70)
    
    mock_agent = CodingAgent(agent_type="mock")
    assert mock_agent.check_agent_available() == True
    
    aider_agent = CodingAgent(agent_type="aider")
    aider_available = aider_agent.check_agent_available()
    print(f"  Aider available: {aider_available}")
    
    claude_agent = CodingAgent(agent_type="claude-code")
    claude_available = claude_agent.check_agent_available()
    print(f"  Claude-code available: {claude_available}")
    
    print("✓ Agent availability test passed\n")


def test_timeout_handling():
    print("\n" + "="*70)
    print("TEST 4: Timeout Handling")
    print("="*70)

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = CodingAgent(agent_type="mock", timeout=1, working_dir=tmpdir)
        result = agent.execute("Test prompt")

        assert result.success == True
        assert result.execution_time < 2.0
    
    print("✓ Timeout handling test passed\n")


def test_error_handling():
    print("\n" + "="*70)
    print("TEST 5: Error Handling")
    print("="*70)
    
    try:
        agent = CodingAgent(agent_type="invalid_agent")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid_agent" in str(e)
        print("✓ Invalid agent type raises error")
    
    print("✓ Error handling test passed\n")


def test_agent_result_structure():
    print("\n" + "="*70)
    print("TEST 6: AgentResult Structure")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = CodingAgent(agent_type="mock", working_dir=tmpdir)
        result = agent.execute("Test")
    
    assert hasattr(result, "success")
    assert hasattr(result, "output")
    assert hasattr(result, "error")
    assert hasattr(result, "execution_time")
    assert hasattr(result, "exit_code")
    assert hasattr(result, "changes_made")
    
    assert isinstance(result.success, bool)
    assert isinstance(result.output, str)
    assert isinstance(result.error, str)
    assert isinstance(result.execution_time, float)
    assert isinstance(result.exit_code, int)
    assert isinstance(result.changes_made, bool)
    
    print("✓ AgentResult structure test passed\n")


if __name__ == "__main__":
    test_initialization()
    test_mock_agent()
    test_agent_availability()
    test_timeout_handling()
    test_error_handling()
    test_agent_result_structure()
    print("\n" + "="*70)
    print("ALL CODING AGENT TESTS PASSED")
    print("="*70 + "\n")

