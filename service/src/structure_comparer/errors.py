class ProjectAlreadyExists(Exception):
    def __init__(self, msg="Project with same name already exists", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class ProjectNotFound(Exception):
    def __init__(self, msg="Project not found", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class PackageNotFound(Exception):
    def __init__(self, msg="Package not found", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class ComparisonNotFound(Exception):
    def __init__(self, msg="Comparison not found", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MappingNotFound(Exception):
    def __init__(self, msg="Mapping not found", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MappingTargetNotFound(Exception):
    def __init__(self, msg="Target not found", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class FieldNotFound(Exception):
    def __init__(self, msg="Field not found", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MappingActionNotAllowed(Exception):
    def __init__(self, msg="Mapping action not allowed", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MappingTargetMissing(Exception):
    def __init__(self, msg="Mapping target missing", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MappingValueMissing(Exception):
    def __init__(self, msg="Mapping value missing", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class InitializationError(Exception):
    pass


class NotInitialized(Exception):
    def __init__(self, msg="Instance was not initialized (correctly)", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class NotAllowed(Exception):
    def __init__(self, msg="Operation not allowed", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class InvalidFileFormat(Exception):
    def __init__(
        self, msg="A file with an incorrect format was provided", *args, **kwargs
    ):
        super().__init__(msg, *args, **kwargs)


class PackageCorrupted(Exception):
    def __init__(self, msg="Package is corrupted", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class PackageNoSnapshots(Exception):
    def __init__(self, msg="Package does not contain snapshots", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class PackageAlreadyExists(Exception):
    def __init__(self, msg="Package already exists", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
