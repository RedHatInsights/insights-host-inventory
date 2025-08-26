from app.models.system_profile_transformer import split_system_profile_data
from tests.helpers.test_utils import get_sample_dynamic_profile_data
from tests.helpers.test_utils import get_sample_profile_data
from tests.helpers.test_utils import get_sample_static_profile_data


class TestSystemProfileTransformer:
    """Test the system profile transformation utilities."""

    def test_split_system_profile_data_empty(self):
        """Test splitting empty system profile data."""
        static, dynamic = split_system_profile_data({})
        assert static == {}
        assert dynamic == {}

    def test_split_system_profile_data_static_only(self):
        """Test splitting system profile data with only static fields."""
        input_data = get_sample_static_profile_data()

        static, dynamic = split_system_profile_data(input_data)

        assert static == input_data
        assert dynamic == {}

    def test_split_system_profile_data_dynamic_only(self):
        """Test splitting system profile data with only dynamic fields."""
        input_data = get_sample_dynamic_profile_data()

        static, dynamic = split_system_profile_data(input_data)

        assert static == {}
        assert dynamic == input_data

    def test_split_system_profile_data_mixed(self):
        """Test splitting system profile data with mixed fields."""
        input_static, input_dynamic = get_sample_profile_data()

        static, dynamic = split_system_profile_data(input_static | input_dynamic)

        expected_static = input_static
        expected_dynamic = input_dynamic

        assert static == expected_static
        assert dynamic == expected_dynamic
