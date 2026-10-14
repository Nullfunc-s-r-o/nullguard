# Build Stage
FROM python:3.12-slim AS builder

WORKDIR /build

# Install C++ build dependencies
RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire source tree
COPY . .

# Create a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Build the C++ extension
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --parallel

# Install Python package (standard, non-editable)
RUN pip install .

# Copy C++ extension to the virtual environment's site-packages
RUN SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])") && \
    cp nullguard_core*.so "$SITE_PACKAGES/"

# Runtime Stage
FROM python:3.12-slim

WORKDIR /app

# Copy the pre-built virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Setup default environment variables
ENV NULLGUARD_DB="/app/data/nullguard_state.db"
ENV NULLGUARD_CONFIG="/app/config.yaml"
RUN mkdir -p /app/data

# Provide a base configuration file if the user hasn't mounted one
COPY config.example.yaml /app/config.yaml

# Run the daemon in foreground mode so Docker doesn't exit
CMD ["nullguard", "start", "--fg"]
