import logging
from typing import Dict

from .action import Action
from .data.mapping import Mapping
from .helpers import split_parent_child

DICT_MAPPINGS = "mappings"
DICT_FIXED = "fixed"
DICT_REMOVE = "remove"

IGNORE_CLASSIFICATIONS = [
    Action.NOT_USE,
    Action.EMPTY,
    Action.COPY_FROM,
    Action.MEDICATION_SERVICE,
]


logger = logging.getLogger(__name__)


def gen_mapping_dict(structured_mapping: Dict[str, Mapping]):
    result = {}

    # Iterate over the different mappings
    for mappings in structured_mapping.values():
        # Iterate over the source profiles
        # These will be the roots of the mappings
        for source_profile in sorted(mappings.sources):
            profile_handling = {DICT_MAPPINGS: {}, DICT_FIXED: {}, DICT_REMOVE: []}
            for field, presences in mappings.fields.items():

                # If classification is the same as the parent, do not handle this entry
                parent, _ = split_parent_child(field)
                comparison_parent = mappings.fields.get(parent)
                if (
                    comparison_parent is not None
                    and presences.action == comparison_parent.action
                ):
                    continue

                # If 'manual' and should always be set to a fixed value
                if presences.action == Action.FIXED:
                    profile_handling[DICT_FIXED][field] = presences.fixed

                # Otherwise only if value is present
                elif presences.profiles[source_profile.key].present:
                    # If field should be used and remark was not changed
                    action_info = presences.action_info
                    user_remark = action_info.user_remark if action_info else None
                    if (
                        presences.action in [Action.USE, Action.EXTENSION]
                        and not user_remark
                    ):
                        # Put value in the same field
                        profile_handling[DICT_MAPPINGS][field] = field

                    # If 'copy_to' get the target field from extra field
                    elif presences.action == Action.COPY_TO:
                        profile_handling[DICT_MAPPINGS][field] = presences.other

                    # Do not handle when classification should be ignored,
                    # or add to ignore if parent was not ignored or fixed
                    elif presences.action in IGNORE_CLASSIFICATIONS:
                        if (
                            parent_field := mappings.fields.get(parent)
                        ) and parent_field.action in [
                            Action.USE,
                            Action.EXTENSION,
                            Action.COPY_TO,
                        ]:
                            profile_handling[DICT_REMOVE].append(field)

                    else:
                        # Log fall-through
                        remark_for_log = ""
                        if action_info:
                            remark_for_log = action_info.user_remark or action_info.system_remark or ""
                        logger.warning(
                            "gen_mapping_dict: did not handle %s:%s:%s:%s %s",
                            source_profile.key,
                            mappings.target.key,
                            field,
                            presences.action,
                            remark_for_log,
                        )

            if source_profile.key not in result:
                result[source_profile.key] = {}
            result[source_profile.key][mappings.target.key] = {
                "id": mappings.id,
                "version": mappings.version,
                "status": mappings.status,
                "last_updated": mappings.last_updated,
                "mappings": profile_handling[DICT_MAPPINGS],
                "fixed": profile_handling[DICT_FIXED],
                "remove": profile_handling[DICT_REMOVE],
            }

    return result
