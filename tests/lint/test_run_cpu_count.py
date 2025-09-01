# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/PyCQA/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/PyCQA/pylint/blob/main/CONTRIBUTORS.txt

"""Tests for the CPU counting functions in run.py."""

from unittest.mock import mock_open, patch

import pytest

from pylint.lint.run import _cpu_count, _query_cpu


class TestCpuCounting:
    """Test CPU counting functions."""

    def test_query_cpu_kubernetes_scenario(self):
        """Test _query_cpu in Kubernetes environment with cpu.shares = 2."""
        # This reproduces the exact scenario reported in the issue where
        # cpu.cfs_quota_us = -1, cpu.shares = 2, which results in int(2/1024) = 0
        mock_files = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
            "/sys/fs/cgroup/cpu/cpu.shares": "2\n"
        }

        def mock_open_func(filename, *args, **kwargs):
            if filename in mock_files:
                return mock_open(read_data=mock_files[filename])()
            return mock_open()()

        with patch('pathlib.Path.is_file', return_value=True):
            with patch('builtins.open', side_effect=mock_open_func):
                result = _query_cpu()
                assert result == 0, f"Expected 0, got {result}"

    def test_cpu_count_never_returns_zero(self):
        """Test that _cpu_count never returns 0, even when _query_cpu returns 0."""
        # This is the main fix: _cpu_count should never return 0
        with patch('pylint.lint.run._query_cpu', return_value=0):
            with patch('os.sched_getaffinity', return_value=set(range(4))):
                result = _cpu_count()
                assert result >= 1, f"_cpu_count returned {result}, but should never return < 1"

    def test_cpu_count_handles_low_cpu_shares(self):
        """Test _cpu_count with various low cpu_share values."""
        test_cases = [
            (0, 4, 1),  # cpu_share=0 should return at least 1
            (1, 4, 1),  # cpu_share=1, cpu_count=4 should return 1
            (2, 4, 2),  # cpu_share=2, cpu_count=4 should return 2
            (8, 4, 4),  # cpu_share=8, cpu_count=4 should return min(8,4)=4
        ]
        
        for cpu_share, cpu_count_val, expected in test_cases:
            with patch('pylint.lint.run._query_cpu', return_value=cpu_share):
                with patch('multiprocessing.cpu_count', return_value=cpu_count_val):
                    result = _cpu_count()
                    assert result == expected, \
                        f"cpu_share={cpu_share}, cpu_count={cpu_count_val}: expected {expected}, got {result}"

    def test_cpu_count_none_cpu_share(self):
        """Test _cpu_count when _query_cpu returns None."""
        with patch('pylint.lint.run._query_cpu', return_value=None):
            with patch('multiprocessing.cpu_count', return_value=4):
                result = _cpu_count()
                assert result == 4, f"Expected 4 when cpu_share is None, got {result}"

    @pytest.mark.parametrize("cpu_shares,expected_query_result", [
        (2, 0),      # Original failing case: int(2/1024) = 0
        (1024, 1),   # Edge case: int(1024/1024) = 1
        (2048, 2),   # Normal case: int(2048/1024) = 2
        (1, 0),      # Very low shares: int(1/1024) = 0
    ])
    def test_query_cpu_shares_calculation(self, cpu_shares, expected_query_result):
        """Test _query_cpu calculation with different cpu.shares values."""
        mock_files = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
            "/sys/fs/cgroup/cpu/cpu.shares": f"{cpu_shares}\n"
        }

        def mock_open_func(filename, *args, **kwargs):
            if filename in mock_files:
                return mock_open(read_data=mock_files[filename])()
            return mock_open()()

        with patch('pathlib.Path.is_file', return_value=True):
            with patch('builtins.open', side_effect=mock_open_func):
                result = _query_cpu()
                assert result == expected_query_result, \
                    f"cpu_shares={cpu_shares}: expected {expected_query_result}, got {result}"