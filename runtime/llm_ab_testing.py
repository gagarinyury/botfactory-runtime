"""A/B testing for LLM features"""
import hashlib
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class LLMABTester:
    """A/B testing for LLM features like llm_improve"""

    def __init__(self):
        self.ab_configs = {
            "llm_improve": {
                "enabled": True,
                "split_ratio": 0.5,  # 50/50 split
                "variants": {
                    "control": {"llm_improve": False},
                    "treatment": {"llm_improve": True}
                }
            }
        }

    def get_variant(self, feature: str, bot_id: str, user_id: int,
                   session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get A/B test variant for a user

        Args:
            feature: Feature name (e.g., "llm_improve")
            bot_id: Bot ID for segmentation
            user_id: User ID for consistent assignment
            session_id: Optional session ID for more granular assignment

        Returns:
            Dict with variant config and metadata
        """
        if feature not in self.ab_configs:
            logger.warning("ab_test_unknown_feature", feature=feature)
            return {"variant": "control", "config": {}, "assigned": False}

        config = self.ab_configs[feature]

        if not config.get("enabled", False):
            # A/B test disabled, return control
            return {
                "variant": "control",
                "config": config["variants"]["control"],
                "assigned": False,
                "reason": "ab_test_disabled"
            }

        # Create deterministic hash for user assignment
        assignment_key = f"{feature}:{bot_id}:{user_id}"
        if session_id:
            assignment_key += f":{session_id}"

        # Use hash to determine assignment (deterministic)
        hash_value = int(hashlib.md5(assignment_key.encode()).hexdigest()[:8], 16)
        assignment_score = (hash_value % 10000) / 10000.0  # 0.0 to 1.0

        split_ratio = config.get("split_ratio", 0.5)

        if assignment_score < split_ratio:
            variant = "treatment"
        else:
            variant = "control"

        variant_config = config["variants"].get(variant, {})

        result = {
            "variant": variant,
            "config": variant_config,
            "assigned": True,
            "assignment_score": assignment_score,
            "split_ratio": split_ratio
        }

        # Log assignment for analytics
        logger.info("ab_test_assignment",
                   feature=feature,
                   variant=variant,
                   bot_id=bot_id,
                   user_id=user_id,
                   assignment_score=assignment_score)

        return result

    def should_use_llm_improve(self, bot_id: str, user_id: int,
                              base_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Determine if LLM improvement should be used based on A/B test

        Args:
            bot_id: Bot ID
            user_id: User ID
            base_config: Base configuration (can override A/B)

        Returns:
            Dict with decision and metadata
        """
        # Check if explicitly set in base config (overrides A/B)
        if base_config and "llm_improve" in base_config:
            if base_config["llm_improve"] == "ab":
                # Explicitly requesting A/B test
                pass
            else:
                # Explicit boolean value overrides A/B
                return {
                    "use_llm": bool(base_config["llm_improve"]),
                    "source": "explicit_config",
                    "variant": None,
                    "ab_test": False
                }

        # Run A/B test
        ab_result = self.get_variant("llm_improve", bot_id, user_id)

        use_llm = ab_result["config"].get("llm_improve", False)

        return {
            "use_llm": use_llm,
            "source": "ab_test",
            "variant": ab_result["variant"],
            "ab_test": True,
            "assignment_score": ab_result.get("assignment_score"),
            "assigned": ab_result["assigned"]
        }

    def record_experiment_result(self, feature: str, variant: str,
                               bot_id: str, user_id: int,
                               outcome: str, metrics: Optional[Dict[str, Any]] = None):
        """
        Record A/B test experiment result for analysis

        Args:
            feature: Feature being tested
            variant: Variant name (control/treatment)
            bot_id: Bot ID
            user_id: User ID
            outcome: Outcome type (e.g., "completion", "error", "timeout")
            metrics: Additional metrics dict
        """
        event_data = {
            "feature": feature,
            "variant": variant,
            "outcome": outcome,
            "bot_id": bot_id,
            "user_id": user_id
        }

        if metrics:
            event_data["metrics"] = metrics

        logger.info("ab_test_result", **event_data)

    def get_experiment_stats(self, feature: str) -> Dict[str, Any]:
        """
        Get current A/B test configuration and stats

        Args:
            feature: Feature name

        Returns:
            Dict with configuration and stats
        """
        if feature not in self.ab_configs:
            return {"error": "Feature not found"}

        config = self.ab_configs[feature]

        return {
            "feature": feature,
            "enabled": config.get("enabled", False),
            "split_ratio": config.get("split_ratio", 0.5),
            "variants": list(config.get("variants", {}).keys()),
            "config": config
        }

    def update_experiment_config(self, feature: str,
                               enabled: Optional[bool] = None,
                               split_ratio: Optional[float] = None):
        """
        Update A/B test configuration (for admin/debugging)

        Args:
            feature: Feature name
            enabled: Whether to enable the test
            split_ratio: Split ratio for treatment group
        """
        if feature not in self.ab_configs:
            logger.warning("ab_test_config_update_unknown_feature", feature=feature)
            return False

        config = self.ab_configs[feature]

        if enabled is not None:
            config["enabled"] = enabled
            logger.info("ab_test_config_updated", feature=feature, enabled=enabled)

        if split_ratio is not None:
            if 0.0 <= split_ratio <= 1.0:
                config["split_ratio"] = split_ratio
                logger.info("ab_test_config_updated", feature=feature, split_ratio=split_ratio)
            else:
                logger.warning("ab_test_invalid_split_ratio", feature=feature, split_ratio=split_ratio)
                return False

        return True

    def force_variant(self, feature: str, bot_id: str, user_id: int, variant: str) -> bool:
        """
        Force a specific variant for a user (for testing/debugging)

        Args:
            feature: Feature name
            bot_id: Bot ID
            user_id: User ID
            variant: Variant to force

        Returns:
            Success boolean
        """
        # In a real implementation, this would store the override in Redis/DB
        # For now, just log it
        logger.info("ab_test_variant_forced",
                   feature=feature,
                   bot_id=bot_id,
                   user_id=user_id,
                   variant=variant)
        return True


# Global A/B tester instance
llm_ab_tester = LLMABTester()