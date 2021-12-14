import random
from typing import List, Tuple, Union, Optional
from core.abc.frame import AbstractFrame, AbstractFrameStorage, FrameType
from core.abc.station import AbstractStation

from core.timeline import TimeLine, TimeParticipant
from utils.helper import get_circle, get_distance
from constant import (
    FRAME_SIZE,
)


class FrameRadius(TimeParticipant):
    def __init__(self, location: Tuple[int, int]):
        self.location = location


class DrawRadiusMixin:
    radius: List[FrameRadius] = []

    def delete_radius(self):
        for radius in self.radius:
            radius.unregister()
        self.radius = []

    def draw_radius(self):
        radius = get_distance(self.location, self.sender.location)
        points = get_circle(self.sender.location, radius)
        for point in points:
            path = FrameRadius(point)
            path.register()
            self.radius.append(path)


class Frame(AbstractFrame, DrawRadiusMixin, TimeParticipant):
    typ = "DATA"
    size = FRAME_SIZE
    sent = None
    vanished = None
    collision = False
    is_duplicate = False

    def __init__(
        self,
        id: str,
        sender: AbstractStation,
        receiver: AbstractStation,
        typ: FrameType,
        duration: Optional[int] = None,
    ):
        self.id = id
        self.sender = sender
        self.receiver = receiver
        self.typ = typ
        self.duration = duration
        self.propagation_speed = sender.medium.propagation_speed
        self.max_range = sender.detect_range

    def is_equal(self, frame: AbstractFrame) -> bool:
        return frame.id == self.id

    def depart(self):
        self.register()
        self.sender.medium.add_frame(self)
        self.sent = self.timeline.current

    def arrive(self, station: AbstractStation):
        station.transmitter.on_detect(self)

    def vanish(self):
        self.vanished = self.timeline.current
        self.delete_radius()
        self.unregister()

    def collide(self):
        self.collision = True

    @property
    def moved(self) -> float:
        return min(
            (self.timeline.current - self.sent) * self.propagation_speed,
            self.max_range,
        )

    @property
    def location(self) -> Tuple[int, int]:
        distance = self.distance
        moved = self.moved
        return (
            int(
                self.sender.location[0]
                + (self.receiver.location[0] - self.sender.location[0])
                * moved
                / distance
            ),
            int(
                self.sender.location[1]
                + (self.receiver.location[1] - self.sender.location[1])
                * moved
                / distance
            ),
        )

    @property
    def distance(self) -> float:
        return get_distance(self.sender.location, self.receiver.location)

    @staticmethod
    def assemble(
        receiver: "AbstractStation",
        sender: "AbstractStation",
        typ: FrameType = "DATA",
        duration: Optional[int] = None,
    ) -> "Frame":
        return Frame(
            id=str(random.randint(0, 1000000)),
            receiver=receiver,
            sender=sender,
            typ=typ,
            duration=duration,
        )

    def duplicate(self):
        frame = self.assemble(
            receiver=self.receiver,
            sender=self.sender,
            typ=self.typ,
            duration=self.duration,
        )
        frame.id = self.id
        frame.is_duplicate = True
        return frame

    def __str__(self) -> str:
        return f"{self.typ} {self.sender.id} -> {self.receiver.id}"

    def icon(self) -> str:
        if self.collision:
            return "XX"
        return f"█{self.typ[0]}"

    def on_tick(self, step: int):
        if not self.sent:
            return

        self.delete_radius()
        self.draw_radius()


class FrameStorage(AbstractFrameStorage):
    def __init__(self, size: int = None):
        self.frames: List[Frame] = []
        self.size = size

    def is_empty(self) -> bool:
        return len(self.frames) == 0

    def is_full(self) -> bool:
        if self.size is None:
            return False
        return len(self.frames) == self.size

    def count(self) -> int:
        return len(self.frames)

    def all(self) -> List[Frame]:
        return self.frames

    def get(self):
        try:
            return self.frames[0]
        except IndexError:
            return None

    def push(self, frame):
        if self.is_full():
            return
        self.frames.append(frame)

    def pop(self):
        try:
            return self.frames.pop(0)
        except IndexError:
            return None
