"""
Torch compatibility patch for LangGraph agent execution.
"""

from contextlib import contextmanager


@contextmanager
def safe_torch_classes_patch():
    """
    Patch torch.classes to avoid crashes on __path__ attribute access.

    Restores original torch.classes after the protected block.
    """
    orig_torch_classes = None
    try:
        import torch

        if hasattr(torch, "classes"):
            orig_torch_classes = torch.classes
            dummy_class = type("_DummyTorchClass", (), {})
            dummy_ns = type("_DummyNs", (), {"__getattr__": lambda self, _: dummy_class})()

            def safe_getattr(self, name):
                if name == "__path__":
                    return dummy_ns
                try:
                    return getattr(orig_torch_classes, name)
                except Exception:
                    return dummy_ns

            safe_classes = type("_SafeClasses", (), {"__getattr__": safe_getattr})()
            torch.classes = safe_classes
        yield
    except Exception:
        # Keep behavior unchanged: if patch fails, continue without failing invoke.
        yield
    finally:
        if orig_torch_classes is not None:
            try:
                import torch

                torch.classes = orig_torch_classes
            except Exception:
                pass
