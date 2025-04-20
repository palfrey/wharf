from unittest.mock import MagicMock, patch
from apps.views import app_list

class MockCelery:
    def __init__(self, res: str):
        self.res = res

    def get(self):
        return self.res
    
commands = {
    ("apps:list", ): """=====> My Apps
wharf"""
}

def mock_commands(*args):
    if args in commands:
        return MockCelery(commands[args])
    print(args)
    raise Exception

@patch("wharf.tasks.run_ssh_command.delay")
def test_app_list(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    assert app_list() == ["wharf"]