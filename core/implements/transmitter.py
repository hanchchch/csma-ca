from typing import Type
from constant import ONE_SECOND
from core.abc.frame import AbstractFrame, AbstractFrameStorage
from core.abc.transmitter import AbstractTransmitter
from core.abc.csma import AbstractCSMA


class Transmitter(AbstractTransmitter):
    def __init__(
        self,
        station_id: int,
        data_rate: int,
        send_queue_size: int,
        recv_queue_size: int,
        with_rts: bool,
        frame_storage: Type[AbstractFrameStorage],
        csma: Type[AbstractCSMA],
    ):
        self.station_id = station_id
        self.data_rate = data_rate
        self.send_frames = frame_storage(send_queue_size)
        self.recv_frames = frame_storage(recv_queue_size)
        self.detected_frames = frame_storage()
        self.with_rts = with_rts
        self.recv = []
        self.recv_current = 0
        self.sent = []
        self.sent_current = 0
        self.collisions = 0
        self.last_sent = None
        self.wasted = 0
        self.csma = csma(data_rate=self.data_rate)
        self.timeout = self.csma.sifs_amount + 2 * self.csma.frame_time

    def add_recv_record(self, frame: AbstractFrame):
        i = 0
        for record in self.recv:
            if record["typ"] == frame.typ:
                self.recv[i]["count"] += 1
                self.recv[i]["size"] += frame.size
                break
            i += 1
        self.recv.append({"typ": frame.typ, "count": 1, "size": frame.size})

    def add_sent_record(self, frame: AbstractFrame):
        i = 0
        for record in self.sent:
            if record["typ"] == frame.typ:
                self.sent[i]["count"] += 1
                self.sent[i]["size"] += frame.size
                break
            i += 1
        self.sent.append({"typ": frame.typ, "count": 1, "size": frame.size})

    def on_receive_success(self):
        frame = self.recv_frames.pop()
        self.add_recv_record(frame)
        self.recv_current = 0
        if frame.typ == "DATA":
            self.on_data(frame)
        elif frame.typ == "ACK":
            self.on_ack(frame)
        elif frame.typ == "RTS":
            self.on_rts(frame)
        elif frame.typ == "CTS":
            self.on_cts(frame)
        return

    def on_receive_failure(self):
        self.recv_frames.pop()
        self.recv_current = 0

    def on_timeout(self):
        self.collisions += 1
        self.wasted += self.timeout
        self.csma.collision_occured()

    def on_detect(self, frame: AbstractFrame):
        self.detected_frames.push(frame)
        if not self.talkover_detected():
            if frame.typ == "CTS":
                self.recv_frames.push(frame)
            elif frame.typ == "RTS":
                self.recv_frames.push(frame)
            elif frame.receiver.id == self.station_id:
                self.recv_frames.push(frame)

    def talkover_detected(self) -> bool:
        return self.detected_frames.count() > 1

    def is_medium_busy(self) -> bool:
        if not self.detected_frames.is_empty():
            return True
        return False

    def is_receiving(self) -> bool:
        return self.recv_frames.count() > 0

    def proceed_recv(self, step: int):
        frame = self.recv_frames.get()

        if self.detected_frames.is_empty():
            # some data frame is lost, most likely due to collision
            self.on_receive_failure()
        elif self.talkover_detected():
            # talkover (collision) occurs
            pass
        elif self.detected_frames.get().id != frame.id:
            # receiving frame ended, and detected frame is the one which made the collision
            self.on_receive_failure()
        else:
            received = step * self.data_rate / ONE_SECOND
            self.recv_current += received

            if self.recv_current >= frame.size:
                self.on_receive_success()

    def push(self, frame: AbstractFrame):
        if self.csma.is_difs(self.with_rts, frame):
            self.csma.set_difs()
        else:
            self.csma.set_sifs()

        queued = self.send_frames.get()
        if queued and self.csma.is_difs(self.with_rts, queued):
            self.send_frames.pop()
        self.send_frames.push(frame)

    def want_to_send(self) -> bool:
        return self.send_frames.get() is not None

    def is_sending(self) -> bool:
        return self.sent_current != 0

    def send(self, step: int):
        frame = self.send_frames.get()
        frame.depart()
        if frame.typ != "ACK":
            self.last_sent = frame
        self.proceed_send(step)

    def proceed_send(self, step: int):
        frame = self.send_frames.get()
        sent = step * self.data_rate / ONE_SECOND

        self.sent_current += sent

        if self.sent_current > frame.size:
            frame.done()
            self.add_sent_record(frame)
            self.sent_current = 0
            self.send_frames.pop()

    def on_data(self, frame: AbstractFrame):
        self.csma.set_sifs()
        ack_frame = frame.assemble(
            receiver=frame.sender,
            sender=frame.receiver,
            typ="ACK",
        )
        self.push(ack_frame)
        self.last_sent = None

    def on_ack(self, frame: AbstractFrame):
        self.csma.reset_backoff_range()
        self.csma.set_difs()
        self.last_sent = None

    def on_rts(self, frame: AbstractFrame):
        if frame.receiver.id == self.station_id:
            self.csma.set_sifs()
            cts_frame = frame.assemble(
                receiver=frame.sender,
                sender=frame.receiver,
                typ="CTS",
                duration=self.csma.cts_duration,
            )
            self.push(cts_frame)
        else:
            self.csma.set_nav(frame.duration)

    def on_cts(self, frame: AbstractFrame):
        if frame.receiver.id == self.station_id:
            self.csma.reset_backoff_range()
            self.csma.set_sifs()
            data_frame = frame.assemble(
                receiver=frame.sender,
                sender=frame.receiver,
                typ="DATA",
            )
            self.push(data_frame)
            self.csma.set_allocated(frame.duration)
            self.last_sent = None
        else:
            self.csma.set_nav(frame.duration)

    def is_acked(self) -> bool:
        return self.last_sent is None

    def timeout_occured(self, current: int):
        if not self.is_acked():
            if self.last_sent.sent + self.timeout < current:
                self.last_sent = None
                return True
        return False

    def okay_to_send(self, step: int) -> bool:
        if self.is_acked():
            is_busy = self.is_medium_busy()
            csma_ok = self.csma.check_and_decrease(is_busy, step)
            return (not is_busy) and csma_ok
        return False
