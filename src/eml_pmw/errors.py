class PMWFabricError(RuntimeError):
    pass

class IdentityConflictError(PMWFabricError):
    pass

class ResourceConflictError(PMWFabricError):
    pass

class UnsafeIntegrationError(PMWFabricError):
    pass

class ProviderUnavailableError(PMWFabricError):
    pass

class UnsupportedProjectionError(PMWFabricError):
    pass
