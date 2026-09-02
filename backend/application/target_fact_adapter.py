"""Internal identity boundary between Slice 3 targets and Product Fact reads."""

from backend.common import ObjectScope, TurnRequest
from backend.conversation import TargetResolution, TurnTargetKind


class TargetFactIdentityError(ValueError):
    """A resolved target cannot safely enter the Product Fact flow."""


class TargetFactIdentityAdapter:
    """Forward only a same-store, fully resolved single-object identity.

    This adapter does not search, rank, or repair identities.  Product and
    Variant ownership remains enforced by the existing exact Shopify-read
    guards after this local boundary.
    """

    def resolve_scope(
        self,
        *,
        request: TurnRequest,
        resolution: TargetResolution,
    ) -> ObjectScope:
        target = resolution.turn_target
        if target.kind is not TurnTargetKind.SINGLE_OBJECT:
            raise TargetFactIdentityError("only SINGLE_OBJECT targets may read facts")
        scope = target.object_scope
        if scope is None:
            raise TargetFactIdentityError(
                "SINGLE_OBJECT target is missing object_scope"
            )
        if scope.store_id != request.store_id:
            raise TargetFactIdentityError("resolved target crossed the request store")
        return scope
