class AppError(Exception):
    pass


class ConfigurationError(AppError):
    pass


class SpotifyApiError(AppError):
    pass


class InvalidSpotifyLinkError(AppError):
    pass


class UnsupportedSpotifyResourceError(AppError):
    pass


class CatalogApiError(AppError):
    pass


class DownloadError(AppError):
    pass
