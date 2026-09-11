from pet_yaya.domain.models import GrowthState


class GrowthEngine:
    """Applies small, deterministic and explainable growth changes."""

    _UNLOCKS = (
        (3, "curious_greeting"),
        (8, "tiny_story"),
        (15, "weekly_growth_card"),
    )

    def record_interaction(self, state: GrowthState) -> GrowthState:
        updated = GrowthState(
            interaction_count=state.interaction_count + 1,
            growth_points=state.growth_points + 1,
            unlocked_skills=list(state.unlocked_skills),
        )
        for threshold, skill in self._UNLOCKS:
            if (
                updated.interaction_count >= threshold
                and skill not in updated.unlocked_skills
            ):
                updated.unlocked_skills.append(skill)
        return updated


