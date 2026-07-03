"""
Result / Option monad 类型

用于统一处理成功/失败和可选值，减少 try/except 和 None 检查散落。

用法:
    def get_user(id: int) -> Result[User, str]:
        user = db.query(...)
        if user is None:
            return Result.failure(f"用户 {id} 不存在")
        return Result.success(user)

    # 链式处理
    result = get_user(1).map(lambda u: u.username).unwrap_or("未知用户")

    # Option
    opt = Option.some("hello").map(str.upper)  # Some("HELLO")
    opt = Option.nothing().unwrap_or("default")  # "default"
"""

from dataclasses import dataclass
from typing import TypeVar, Generic, Callable

T = TypeVar('T')
E = TypeVar('E')
U = TypeVar('U')


@dataclass(frozen=True)
class Result(Generic[T, E]):
    """Either 模式：成功时含值，失败时含错误。"""

    _ok: T | None
    _error: E | None

    @staticmethod
    def success(value: T) -> 'Result[T, E]':
        return Result(_ok=value, _error=None)

    @staticmethod
    def failure(error: E) -> 'Result[T, E]':
        return Result(_ok=None, _error=error)

    def is_ok(self) -> bool:
        return self._error is None

    def is_err(self) -> bool:
        return self._error is not None

    @property
    def ok(self) -> T | None:
        """访问成功值（不抛异常），失败时返回 None"""
        return self._ok

    @property
    def error(self) -> E | None:
        """访问错误值（不抛异常），成功时返回 None"""
        return self._error

    def unwrap(self) -> T:
        """解包成功值，失败时抛异常。仅用于确定不会失败时。"""
        if self._error is not None:
            raise ValueError(f"Called unwrap() on failure: {self._error}")
        return self._ok

    def unwrap_or(self, default: T) -> T:
        return self._ok if self._error is None else default

    def unwrap_err(self) -> E:
        if self._ok is not None:
            raise ValueError(f"Called unwrap_err() on success: {self._ok}")
        return self._error

    def map(self, fn: Callable[[T], U]) -> 'Result[U, E]':
        """成功时变换值，失败时透传错误。"""
        if self._error is not None:
            return Result(_ok=None, _error=self._error)
        return Result.success(fn(self._ok))

    def map_err(self, fn: Callable[[E], U]) -> 'Result[T, U]':
        """失败时变换错误，成功时透传。"""
        if self._error is not None:
            return Result.failure(fn(self._error))
        return self  # type: ignore[return-value]

    def and_then(self, fn: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        """成功时链式调用可能失败的操作，失败时透传。"""
        if self._error is not None:
            return Result(_ok=None, _error=self._error)
        return fn(self._ok)

    def __repr__(self) -> str:
        if self._error is not None:
            return f"Failure({self._error!r})"
        return f"Success({self._ok!r})"

    # 支持 if result: ... 语法（成功为 True）
    def __bool__(self) -> bool:
        return self._error is None


@dataclass(frozen=True)
class Option(Generic[T]):
    """Maybe monad：Some(value) 或 Nothing。"""

    _value: T | None

    @staticmethod
    def some(value: T) -> 'Option[T]':
        return Option(_value=value)

    @staticmethod
    def nothing() -> 'Option[T]':
        return Option(_value=None)

    @classmethod
    def from_nullable(cls, value: T | None) -> 'Option[T]':
        """从可为 null 的值创建 Option"""
        return cls.some(value) if value is not None else cls.nothing()

    def is_some(self) -> bool:
        return self._value is not None

    def is_nothing(self) -> bool:
        return self._value is None

    def unwrap(self) -> T:
        if self._value is None:
            raise ValueError("Called unwrap() on Nothing")
        return self._value

    def unwrap_or(self, default: T) -> T:
        return self._value if self._value is not None else default

    def map(self, fn: Callable[[T], U]) -> 'Option[U]':
        if self._value is None:
            return Option(_value=None)
        return Option.some(fn(self._value))

    def and_then(self, fn: Callable[[T], 'Option[U]']) -> 'Option[U]':
        if self._value is None:
            return Option(_value=None)
        return fn(self._value)

    def __repr__(self) -> str:
        if self._value is None:
            return "Nothing"
        return f"Some({self._value!r})"

    def __bool__(self) -> bool:
        return self._value is not None
