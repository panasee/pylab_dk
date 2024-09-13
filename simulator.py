import numpy as np
import matplotlib.pyplot as plt
from typing import Tuple

class SR830Simul:
    def __init__(self, freq, phi, time_constant, offset):
        """
        define the parameters of the SR830 simulator.
        
        Args:
        freq: float
            The frequency of the signal.
        phi: float
            The initial phase of the signal.
        time_constant: float
            The time constant of the measurement.
        """
        self.frequency = freq
        self.phase = phi
        self.time_constant = time_constant
        self.offset = offset

    def generate_signal(self, time_arr, amp, noise_level):
        """
        generate the source signal with noise.

        Args:
        time_arr: numpy array
            The time array.
        amp: float
            The amplitude of the signal.
        noise_level: float
            The noise level of the signal (0 for no noise).
        """
        signal = amp * np.sin(2 * np.pi * self.frequency * time_arr + self.phase) + self.offset
        noise = noise_level * np.random.randn(len(time_arr))
        return signal + noise

    def demodulate_win_avg(self, signal, time_arr, *, order=1):
        reference_x = np.sin(2 * np.pi * order * self.frequency * time_arr)
        reference_y = np.cos(2 * np.pi * order * self.frequency * time_arr)
        
        x = signal * reference_x
        y = signal * reference_y
        
        # Apply low-pass filter (simple moving average for demonstration)
        window_size = int(self.time_constant * len(time_arr) / (time_arr[-1] - time_arr[0]))
        x_filtered = np.convolve(x, np.ones(window_size)/window_size, mode='same')
        y_filtered = np.convolve(y, np.ones(window_size)/window_size, mode='same')
        
        return x_filtered, y_filtered

    def demodulate_win_fft(self, signal: np.ndarray, time_arr: np.ndarray) -> Tuple[np.ndarray]:
        """
        use fft window to demodulate the signal. The output is the x and y components of the demodulated signal and fft frequencies(all orders)
        """
        # Apply low-pass filter (FFT for demonstration)
        window_size = int(self.time_constant * len(time_arr) / (time_arr[-1] - time_arr[0]))
        n_windows = len(signal) - window_size + 1
        fft_result = []

        for i in range(n_windows):
            window = signal[i:i + window_size]
            fft_result.append(np.fft.fft(window))
        x_fft = np.real(np.array(fft_result))
        y_fft = np.imag(np.array(fft_result))

        freqs = np.fft.fftfreq(window_size, time_arr[1] - time_arr[0])
        
        return x_fft, y_fft, freqs



    def calculate_amplitude_phase(self, x, y):
        amplitude = np.sqrt(x**2 + y**2)
        phase = np.arctan2(y, x)
        return amplitude, phase


if __name__ == "__main__":
    # Set up simulation parameters
    frequency = 1000  # Hz
    phase = np.pi / 4  # radians
    time_constant = 0.1  # seconds
    duration = 1  # seconds
    sample_rate = 100000  # Hz

    # Create time array
    time = np.linspace(0, duration, int(duration * sample_rate))

    # Create SR830 simulator
    sr830 = SR830Simul(frequency, phase, time_constant)

    # Generate input signal with noise
    input_signal = sr830.generate_signal(time, amplitude=1, noise_level=0.5)

    # Demodulate signal
    x, y = sr830.demodulate(input_signal, time)

    # Calculate amplitude and phase
    amplitude, measured_phase = sr830.calculate_amplitude_phase(x, y)

    # Plot results
    plt.figure(figsize=(12, 8))

    plt.subplot(3, 1, 1)
    plt.plot(time, input_signal)
    plt.title('Input Signal')
    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude')

    plt.subplot(3, 1, 2)
    plt.plot(time, x, label='X')
    plt.plot(time, y, label='Y')
    plt.title('Demodulated Signals')
    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude')
    plt.legend()

    plt.subplot(3, 1, 3)
    plt.plot(time, amplitude)
    plt.title('Calculated Amplitude')
    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude')

    plt.tight_layout()
    plt.show()

    print(f"Measured amplitude: {np.mean(amplitude):.4f}")
    print(f"Measured phase: {np.mean(measured_phase):.4f} radians")