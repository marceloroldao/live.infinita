#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace {
constexpr int kSampleRate = 48000;
constexpr int kChannels = 2;
constexpr int kChunkFrames = 960;
constexpr double kChunkSeconds = static_cast<double>(kChunkFrames) / kSampleRate;
constexpr float kPi = 3.14159265358979323846f;
std::atomic<bool> g_stop{false};

struct WorldState {
    std::string biome = "forest";
    std::string period = "day";
    std::string weather = "clear";
    bool fire_lit = false;
    float fire_distance = 999.0f;
    bool walking = false;
};

struct Metrics {
    uint64_t chunks = 0;
    uint64_t deadline_misses = 0;
    uint64_t xruns = 0;
    uint64_t voice_chunks = 0;
    double render_sum_ms = 0.0;
    double render_max_ms = 0.0;
    double max_late_ms = 0.0;
};

uint32_t rng_state = 0x91e10da5u;
inline float fast_noise() {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return (static_cast<float>(rng_state & 0xffffu) / 32767.5f) - 1.0f;
}

inline int16_t clip16(float value) {
    value = std::clamp(value, -32768.0f, 32767.0f);
    return static_cast<int16_t>(value);
}

std::vector<std::string> split(const std::string& value, char delimiter) {
    std::vector<std::string> out;
    std::stringstream ss(value);
    std::string item;
    while (std::getline(ss, item, delimiter)) out.push_back(item);
    return out;
}

float parse_float(const std::string& value, float fallback) {
    try { return std::stof(value); } catch (...) { return fallback; }
}

bool parse_bool(const std::string& value) {
    return value == "1" || value == "true" || value == "yes";
}

std::string shell_quote(const std::string& value) {
    std::string out = "'";
    for (char c : value) {
        if (c == '\'') out += "'\\''";
        else out += c;
    }
    out += "'";
    return out;
}

class Mixer {
public:
    Mixer(float ambient, float ducked, float narration)
        : ambient_volume_(ambient), ducked_volume_(ducked), narration_volume_(narration) {}

    void set_state(const WorldState& state) { state_ = state; }

    bool queue_voice_file(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        if (!file) return false;
        file.seekg(0, std::ios::end);
        const auto size = file.tellg();
        if (size <= 0 || size > 64 * 1024 * 1024) return false;
        file.seekg(0, std::ios::beg);
        std::vector<int16_t> samples(static_cast<size_t>(size) / sizeof(int16_t));
        file.read(reinterpret_cast<char*>(samples.data()), static_cast<std::streamsize>(samples.size() * sizeof(int16_t)));
        if (!file && !file.eof()) return false;
        if (samples.size() < 2) return false;
        if (voice_queue_.size() >= 8) voice_queue_.pop_front();
        voice_queue_.push_back(std::move(samples));
        std::error_code ec;
        std::filesystem::remove(path, ec);
        return true;
    }

    bool voice_active() const { return current_voice_ != nullptr || !voice_queue_.empty(); }

    void render(int16_t* output, int frames) {
        bool chunk_voice = voice_active();
        if (chunk_voice) ++voice_chunks_;
        for (int i = 0; i < frames; ++i) {
            float voice_l = 0.0f, voice_r = 0.0f;
            bool speaking = next_voice(voice_l, voice_r);
            const float target_duck = speaking ? std::clamp(ducked_volume_ / std::max(ambient_volume_, 0.0001f), 0.0f, 1.0f) : 1.0f;
            const float smoothing = speaking ? 0.010f : 0.0017f;
            duck_gain_ += (target_duck - duck_gain_) * smoothing;

            float ambient_l = 0.0f, ambient_r = 0.0f;
            if (!speaking) ambient(ambient_l, ambient_r);

            output[i * 2] = clip16(ambient_l + voice_l);
            output[i * 2 + 1] = clip16(ambient_r + voice_r);
        }
    }

    uint64_t voice_chunks() const { return voice_chunks_; }

private:
    bool next_voice(float& left, float& right) {
        if (!current_voice_) {
            if (voice_queue_.empty()) return false;
            current_voice_ = &voice_queue_.front();
            voice_offset_ = 0;
        }
        if (voice_offset_ + 1 >= current_voice_->size()) {
            voice_queue_.pop_front();
            current_voice_ = nullptr;
            voice_offset_ = 0;
            return next_voice(left, right);
        }
        left = static_cast<float>((*current_voice_)[voice_offset_]) * narration_volume_;
        right = static_cast<float>((*current_voice_)[voice_offset_ + 1]) * narration_volume_;
        voice_offset_ += 2;
        if (voice_offset_ >= current_voice_->size()) {
            voice_queue_.pop_front();
            current_voice_ = nullptr;
            voice_offset_ = 0;
        }
        return true;
    }

    inline float oscillator(float& phase, float hz) {
        phase += 2.0f * kPi * hz / static_cast<float>(kSampleRate);
        if (phase >= 2.0f * kPi) phase -= 2.0f * kPi;
        return std::sin(phase);
    }

    void ambient(float& left, float& right) {
        const float noise = fast_noise();
        wind_noise_ = wind_noise_ * 0.9986f + noise * 0.0014f;
        forest_noise_ = forest_noise_ * 0.994f + noise * 0.006f;
        float common = wind_noise_ * 1.7f + oscillator(hum_a_, 48.0f) * 0.045f + oscillator(hum_b_, 71.0f) * 0.025f;
        if (state_.biome == "forest") common += forest_noise_ * 0.46f;
        else if (state_.biome == "field") common += forest_noise_ * 0.26f;
        common *= 0.58f;

        if (state_.period == "night" && (state_.biome == "forest" || state_.biome == "field")) {
            if (--cricket_next_ <= 0) {
                cricket_env_ = 0.16f + (fast_noise() + 1.0f) * 0.10f;
                cricket_next_ = 4800 + static_cast<int>((fast_noise() + 1.0f) * 10800.0f);
            }
            if (cricket_env_ > 0.001f) {
                common += oscillator(cricket_phase_, 3300.0f) * cricket_env_ * 0.025f;
                cricket_env_ *= 0.99972f;
            }
        } else if (state_.biome == "forest" || state_.biome == "field") {
            if (--bird_next_ <= 0) {
                bird_env_ = 0.30f + (fast_noise() + 1.0f) * 0.18f;
                bird_next_ = 80000 + static_cast<int>((fast_noise() + 1.0f) * 60000.0f);
            }
            if (bird_env_ > 0.001f) {
                common += oscillator(bird_phase_, 1900.0f + 350.0f * bird_env_) * bird_env_ * 0.08f;
                bird_env_ *= 0.99955f;
            }
        }

        if (state_.weather == "rain" || state_.weather == "storm" || state_.weather == "drizzle") {
            rain_noise_ = rain_noise_ * 0.78f + fast_noise() * 0.22f;
            common += rain_noise_ * 0.16f;
        }

        if (state_.walking) {
            if (--step_next_ <= 0) {
                step_env_ = 0.65f;
                step_next_ = 20000 + static_cast<int>((fast_noise() + 1.0f) * 1600.0f);
            }
            if (step_env_ > 0.001f) {
                common += (oscillator(step_phase_, 82.0f) * 0.18f + fast_noise() * 0.016f) * step_env_;
                step_env_ *= 0.9987f;
            }
        }

        float fire_l = 0.0f, fire_r = 0.0f;
        if (state_.fire_lit) {
            if (--fire_next_ <= 0) {
                fire_env_ = 0.35f + (fast_noise() + 1.0f) * 0.30f;
                fire_next_ = 1400 + static_cast<int>((fast_noise() + 1.0f) * 3000.0f);
            }
            const float distance_gain = std::clamp(1.0f - state_.fire_distance / 420.0f, 0.12f, 1.0f);
            const float fire = (fast_noise() * fire_env_ * 0.15f + fast_noise() * 0.035f) * distance_gain;
            fire_env_ *= 0.9981f;
            fire_l = fire;
            fire_r = fire;
        }

        // Lightweight procedural tonal bed: one oscillator, changed by biome and night.
        float root = 110.0f;
        if (state_.biome == "river") root = 123.47f;
        else if (state_.biome == "village") root = 130.81f;
        else if (state_.biome == "field") root = 146.83f;
        if (state_.period == "night") root *= 0.5f;
        const float music = oscillator(music_phase_, root) * 0.018f;

        const float gain = 32767.0f * ambient_volume_ * duck_gain_;
        left = (common + fire_l + music) * gain;
        right = (common + fire_r + music) * gain;
    }

    WorldState state_;
    float ambient_volume_ = 0.075f;
    float ducked_volume_ = 0.025f;
    float narration_volume_ = 0.95f;
    float duck_gain_ = 1.0f;
    float wind_noise_ = 0.0f, forest_noise_ = 0.0f, rain_noise_ = 0.0f;
    float hum_a_ = 0.0f, hum_b_ = 0.0f, bird_phase_ = 0.0f, cricket_phase_ = 0.0f;
    float step_phase_ = 0.0f, music_phase_ = 0.0f;
    float bird_env_ = 0.0f, cricket_env_ = 0.0f, fire_env_ = 0.0f, step_env_ = 0.0f;
    int bird_next_ = 48000, cricket_next_ = 18000, fire_next_ = 3200, step_next_ = 0;
    std::deque<std::vector<int16_t>> voice_queue_;
    std::vector<int16_t>* current_voice_ = nullptr;
    size_t voice_offset_ = 0;
    uint64_t voice_chunks_ = 0;
};

void write_metrics(const std::string& path, const Metrics& metrics, const Mixer& mixer) {
    if (path.empty()) return;
    const std::string tmp = path + ".tmp";
    std::ofstream out(tmp, std::ios::trunc);
    if (!out) return;
    const double avg = metrics.chunks ? metrics.render_sum_ms / static_cast<double>(metrics.chunks) : 0.0;
    out << "engine=cpp-native\n";
    out << "sample_rate=" << kSampleRate << "\n";
    out << "chunk_frames=" << kChunkFrames << "\n";
    out << "chunk_ms=20\n";
    out << "chunks=" << metrics.chunks << "\n";
    out << "deadline_misses=" << metrics.deadline_misses << "\n";
    out << "xruns=" << metrics.xruns << "\n";
    out << "voice_chunks=" << mixer.voice_chunks() << "\n";
    out << "render_avg_ms=" << avg << "\n";
    out << "render_max_ms=" << metrics.render_max_ms << "\n";
    out << "max_late_ms=" << metrics.max_late_ms << "\n";
    out << "voice_active=" << (mixer.voice_active() ? 1 : 0) << "\n";
    out.close();
    std::error_code ec;
    std::filesystem::rename(tmp, path, ec);
}

int make_control_socket(const std::string& path) {
    int fd = ::socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) return -1;
    ::unlink(path.c_str());
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path.c_str());
    if (::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        ::close(fd);
        return -1;
    }
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    return fd;
}

void handle_control(int fd, Mixer& mixer) {
    char buffer[4096];
    while (true) {
        const ssize_t n = recv(fd, buffer, sizeof(buffer) - 1, 0);
        if (n <= 0) break;
        buffer[n] = '\0';
        const std::string message(buffer);
        const auto parts = split(message, '|');
        if (parts.empty()) continue;
        if (parts[0] == "STATE" && parts.size() >= 7) {
            WorldState state;
            state.biome = parts[1];
            state.period = parts[2];
            state.weather = parts[3];
            state.fire_lit = parse_bool(parts[4]);
            state.fire_distance = parse_float(parts[5], 999.0f);
            state.walking = parse_bool(parts[6]);
            mixer.set_state(state);
        } else if (parts[0] == "VOICE" && parts.size() >= 2) {
            if (!mixer.queue_voice_file(parts[1])) std::cerr << "[audio-native] failed voice file " << parts[1] << "\n";
        } else if (parts[0] == "STOP") {
            g_stop.store(true);
        }
    }
}

void signal_handler(int) { g_stop.store(true); }

} // namespace

int main(int argc, char** argv) {
    std::string socket_path = "/var/lib/live-infinita/audio/native.sock";
    std::string metrics_path = "/var/lib/live-infinita/audio/native-metrics.txt";
    std::string udp_output = "udp://127.0.0.1:5500?pkt_size=1316";
    float ambient = 0.075f, ducked = 0.025f, narration = 0.95f;
    for (int i = 1; i + 1 < argc; i += 2) {
        const std::string key = argv[i], value = argv[i + 1];
        if (key == "--socket") socket_path = value;
        else if (key == "--metrics") metrics_path = value;
        else if (key == "--udp-output") udp_output = value;
        else if (key == "--ambient") ambient = parse_float(value, ambient);
        else if (key == "--ducked") ducked = parse_float(value, ducked);
        else if (key == "--narration") narration = parse_float(value, narration);
    }

    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    std::filesystem::create_directories(std::filesystem::path(socket_path).parent_path());
    int control_fd = make_control_socket(socket_path);
    if (control_fd < 0) {
        std::cerr << "[audio-native] cannot bind control socket " << socket_path << "\n";
        return 2;
    }

    const std::string ffmpeg = "ffmpeg -hide_banner -loglevel error -f s16le -ar 48000 -ac 2 -i pipe:0 "
        "-c:a aac -b:a 160k -ar 48000 -ac 2 -f mpegts " + shell_quote(udp_output);
    FILE* pipe = popen(ffmpeg.c_str(), "w");
    if (!pipe) {
        std::cerr << "[audio-native] cannot start ffmpeg\n";
        ::close(control_fd);
        ::unlink(socket_path.c_str());
        return 3;
    }
    setvbuf(pipe, nullptr, _IONBF, 0);

    Mixer mixer(ambient, ducked, narration);
    Metrics metrics;
    std::vector<int16_t> chunk(kChunkFrames * kChannels);
    using clock = std::chrono::steady_clock;
    auto next_deadline = clock::now();
    const auto chunk_duration = std::chrono::microseconds(20000);

    std::cout << "[audio-native] started sample_rate=48000 chunk_ms=20 socket=" << socket_path << "\n";
    while (!g_stop.load()) {
        handle_control(control_fd, mixer);
        const auto started = clock::now();
        mixer.render(chunk.data(), kChunkFrames);
        const size_t written = fwrite(chunk.data(), sizeof(int16_t), chunk.size(), pipe);
        if (written != chunk.size()) {
            std::cerr << "[audio-native] ffmpeg pipe closed\n";
            ++metrics.xruns;
            break;
        }
        const auto finished = clock::now();
        const double render_ms = std::chrono::duration<double, std::milli>(finished - started).count();
        ++metrics.chunks;
        metrics.render_sum_ms += render_ms;
        metrics.render_max_ms = std::max(metrics.render_max_ms, render_ms);
        if (render_ms > 20.0) ++metrics.deadline_misses;

        next_deadline += chunk_duration;
        const auto now = clock::now();
        if (now < next_deadline) {
            std::this_thread::sleep_until(next_deadline);
        } else {
            const double late_ms = std::chrono::duration<double, std::milli>(now - next_deadline).count();
            metrics.max_late_ms = std::max(metrics.max_late_ms, late_ms);
            ++metrics.deadline_misses;
            if (late_ms >= 20.0) ++metrics.xruns;
            if (late_ms > 250.0) next_deadline = clock::now();
        }

        if (metrics.chunks % 500 == 0) {
            write_metrics(metrics_path, metrics, mixer);
            const double avg = metrics.render_sum_ms / static_cast<double>(metrics.chunks);
            std::cout << "[audio-native] realtime chunks=" << metrics.chunks
                      << " misses=" << metrics.deadline_misses
                      << " xruns=" << metrics.xruns
                      << " avg_ms=" << avg
                      << " max_ms=" << metrics.render_max_ms
                      << " late_ms=" << metrics.max_late_ms
                      << " voice_chunks=" << mixer.voice_chunks() << "\n";
            std::cout.flush();
        }
    }

    write_metrics(metrics_path, metrics, mixer);
    pclose(pipe);
    ::close(control_fd);
    ::unlink(socket_path.c_str());
    return 0;
}
