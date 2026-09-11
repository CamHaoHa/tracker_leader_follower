#!/usr/bin/env python3

import serial
import time
import os
import struct
import fcntl

# --- CONFIGURATION ---
PORT_BOTTOM = '/dev/ttyS4'
PORT_LEFT = '/dev/ttyS3'
BAUDRATE = 9600
TRIGGER_BYTE = b'\xA0'

MAX_DISTANCE_CM = 30
OBJECT_THRESHOLD_CM = 1.0
NOISE_THRESHOLD_CM = 0.5  # Filter out small movements
MIN_MOVEMENT_CM = 0.5     # Minimum movement to update position
UPDATE_RATE = 0.033  # 30fps target

class FastFramebuffer:
    def __init__(self, device='/dev/fb0'):
        self.fd = os.open(device, os.O_RDWR)
        
        # Detect framebuffer info
        from fcntl import ioctl
        FBIOGET_VSCREENINFO = 0x4600
        var_info = bytearray(160)
        ioctl(self.fd, FBIOGET_VSCREENINFO, var_info)
        
        self.width = struct.unpack('I', var_info[0:4])[0]
        self.height = struct.unpack('I', var_info[4:8])[0]
        self.bpp = struct.unpack('I', var_info[24:28])[0]
        self.stride = self.width * (self.bpp // 8)
        self.buffer_size = self.stride * self.height
        
        print(f"Framebuffer: {self.width}x{self.height} @ {self.bpp}bpp")
        
        # Double buffering - back buffer for drawing
        self.back_buffer = bytearray(self.buffer_size)
        
        # Pre-compute colors
        self.bg_color = self.rgb_to_bytes(0, 0, 0)
        self.object_color = self.rgb_to_bytes(255, 255, 0)
        
        # Calculate scale for range
        self.scale = min(self.width, self.height) / MAX_DISTANCE_CM
        self.origin_x = self.width // 2
        self.origin_y = self.height // 2
        
        # Initialize back buffer with black
        self.clear_back_buffer()

    def rgb_to_bytes(self, r, g, b):
        if self.bpp == 16:
            return struct.pack('H', ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
        else:
            return bytes([b, g, r]) + (b'\x00' if self.bpp == 32 else b'')

    def clear_back_buffer(self):
        """Clear back buffer to black"""
        row_data = self.bg_color * self.width
        for y in range(self.height):
            offset = y * self.stride
            self.back_buffer[offset:offset + len(row_data)] = row_data

    def draw_box_in_buffer(self, x, y, size=15):
        """Draw box in back buffer only"""
        half = size // 2
        for dy in range(-half, half + 1):
            y_pos = y + dy
            if 0 <= y_pos < self.height:
                for dx in range(-half, half + 1):
                    x_pos = x + dx
                    if 0 <= x_pos < self.width:
                        offset = y_pos * self.stride + x_pos * (self.bpp // 8)
                        if offset + len(self.object_color) <= len(self.back_buffer):
                            self.back_buffer[offset:offset + len(self.object_color)] = self.object_color

    def swap_buffers(self):
        """Swap back buffer to front (no flicker)"""
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.write(self.fd, self.back_buffer)

    def close(self):
        os.close(self.fd)

class FastSensorReader:
    def __init__(self, port):
        self.ser = serial.Serial(port, BAUDRATE, timeout=0.01)
        self.last_value = MAX_DISTANCE_CM
        
    def read_distance(self):
        try:
            self.ser.write(TRIGGER_BYTE)
            time.sleep(0.01)
            
            if self.ser.in_waiting >= 3:
                data = self.ser.read(3)
                if len(data) == 3:
                    combined = (data[0] << 16) + (data[1] << 8) + data[2]
                    distance = combined / 10000.0
                    if 2.0 <= distance <= MAX_DISTANCE_CM:
                        self.last_value = distance
                        return distance
        except:
            pass
        return self.last_value

class SmartTracker:
    def __init__(self):
        self.sensor_bottom = FastSensorReader(PORT_BOTTOM)
        self.sensor_left = FastSensorReader(PORT_LEFT)
        self.background_bottom = MAX_DISTANCE_CM
        self.background_left = MAX_DISTANCE_CM
        self.last_pos = None
        self.stable_frames = 0
        self.object_visible = False
        
    def quick_calibrate(self):
        print("Calibrating...")
        bottom_min = MAX_DISTANCE_CM
        left_min = MAX_DISTANCE_CM
        
        for _ in range(3):
            bottom_val = self.sensor_bottom.read_distance()
            left_val = self.sensor_left.read_distance()
            bottom_min = min(bottom_min, bottom_val)
            left_min = min(left_min, left_val)
            time.sleep(0.005)
        
        self.background_bottom = bottom_min
        self.background_left = left_min
        print(f"Calibrated - Bottom:{bottom_min:.1f}cm, Left:{left_min:.1f}cm")
    
    def is_object_in_view(self, bottom_dist, left_dist):
        """Check if object is within sensor range and detectable"""
        # Object is in view if it's significantly closer than background
        bottom_diff = self.background_bottom - bottom_dist
        left_diff = self.background_left - left_dist
        
        return (bottom_diff > OBJECT_THRESHOLD_CM or 
                left_diff > OBJECT_THRESHOLD_CM)
    
    def filter_noise(self, new_pos, current_pos):
        """Apply noise filtering and movement threshold"""
        if current_pos is None:
            return new_pos  # No previous position, accept new one
            
        # Calculate distance moved
        dx = abs(new_pos[0] - current_pos[0])
        dy = abs(new_pos[1] - current_pos[1])
        distance_moved = (dx**2 + dy**2)**0.5
        
        # If movement is below threshold, consider it noise
        if distance_moved < MIN_MOVEMENT_CM:
            self.stable_frames += 1
            # If stable for multiple frames, keep position to filter noise
            if self.stable_frames < 3:
                return current_pos
            else:
                return new_pos  # Accept small movement after stability
        else:
            self.stable_frames = 0
            return new_pos
    
    def read_and_track(self):
        # Read sensors
        bottom = self.sensor_bottom.read_distance()
        left = self.sensor_left.read_distance()
        
        # Check if object is in view
        self.object_visible = self.is_object_in_view(bottom, left)
        
        if not self.object_visible:
            self.last_pos = None
            self.stable_frames = 0
            return False, None, bottom, left
        
        # Object is in view - calculate position
        # Invert bottom: closer object = higher position
        inverted_bottom = MAX_DISTANCE_CM - bottom
        
        x = max(2.0, min(MAX_DISTANCE_CM, left))
        y = max(2.0, min(MAX_DISTANCE_CM, inverted_bottom))
        
        new_pos = (x, y)
        
        # Apply noise filtering
        filtered_pos = self.filter_noise(new_pos, self.last_pos)
        
        # Simple smoothing (only if we have a previous position)
        if self.last_pos:
            # Weighted average for smooth movement
            smooth_x = (filtered_pos[0] + self.last_pos[0] * 2) / 3
            smooth_y = (filtered_pos[1] + self.last_pos[1] * 2) / 3
            final_pos = (smooth_x, smooth_y)
        else:
            final_pos = filtered_pos
        
        self.last_pos = final_pos
        return True, final_pos, bottom, left

def main():
    print("=== SMART OBJECT TRACKER ===")
    print("Noise filtering + Object visibility checking")
    
    fb = FastFramebuffer()
    tracker = SmartTracker()
    
    tracker.quick_calibrate()
    
    print("\nTracking started - smart filtering enabled")
    print("Press Ctrl+C to exit\n")
    
    frame_count = 0
    last_fps_time = time.time()
    fps = 0
    object_shown = False
    
    try:
        while True:
            frame_start = time.time()
            frame_count += 1
            
            # Always start with clean back buffer
            fb.clear_back_buffer()
            
            # Read sensors and track with smart filtering
            object_detected, position, bottom_dist, left_dist = tracker.read_and_track()
            
            if object_detected and position:
                x_cm, y_cm = position
                
                # Convert to screen coordinates (centered)
                screen_x = fb.origin_x + int((x_cm - MAX_DISTANCE_CM/2) * fb.scale)
                screen_y = fb.origin_y + int((y_cm - MAX_DISTANCE_CM/2) * fb.scale)
                
                # Draw box in back buffer
                fb.draw_box_in_buffer(screen_x, screen_y, 20)
                object_shown = True
                
                status = f"OBJECT: X={x_cm:.1f}cm, Y={y_cm:.1f}cm"
            else:
                if object_shown:
                    # Object disappeared - clear display
                    object_shown = False
                status = "NO OBJECT"
            
            # Swap buffers (atomic update - no flicker)
            fb.swap_buffers()
            
            # Calculate FPS
            current_time = time.time()
            if current_time - last_fps_time >= 0.5:
                fps = frame_count / (current_time - last_fps_time)
                frame_count = 0
                last_fps_time = current_time
            
            visibility = "VISIBLE" if tracker.object_visible else "OUT OF VIEW"
            print(f"\rFPS: {fps:.1f} | {status} | {visibility}        ", end="", flush=True)
            
            # Timing control
            elapsed = time.time() - frame_start
            sleep_time = max(0, UPDATE_RATE - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except KeyboardInterrupt:
        print("\n\nExiting...")
    finally:
        # Clear screen on exit
        fb.clear_back_buffer()
        fb.swap_buffers()
        fb.close()
        print("Cleanup complete")

if __name__ == '__main__':
    main()
