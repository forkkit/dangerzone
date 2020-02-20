import os
import stat
import requests
import tempfile
import subprocess
import shutil
import time
import platform
from PyQt5 import QtCore, QtGui, QtWidgets


def is_docker_installed(common):
    if platform.system() == "Darwin":
        # Does the docker binary exist?
        if os.path.isdir("/Applications/Docker.app") and os.path.exists(
            common.container_runtime
        ):
            # Is it executable?
            st = os.stat(common.container_runtime)
            return bool(st.st_mode & stat.S_IXOTH)

    if platform.system() == "Windows":
        return os.path.exists(common.container_runtime)

    return False


def is_docker_ready(common):
    # Run `docker ps` without an error
    try:
        subprocess.run(
            [common.container_runtime, "ps"],
            check=True,
            startupinfo=common.get_subprocess_startupinfo(),
        )
        return True
    except subprocess.CalledProcessError:
        return False


def launch_docker_windows(common):
    docker_desktop_path = "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"
    subprocess.Popen(
        [docker_desktop_path], startupinfo=common.get_subprocess_startupinfo()
    )


class DockerInstaller(QtWidgets.QDialog):
    def __init__(self, common):
        super(DockerInstaller, self).__init__()
        self.common = common

        self.setWindowTitle("dangerzone")
        self.setWindowIcon(QtGui.QIcon(self.common.get_resource_path("logo.png")))

        label = QtWidgets.QLabel()
        if platform.system() == "Darwin":
            label.setText("Dangerzone for macOS requires Docker")
        elif platform.system() == "Windows":
            label.setText("Dangerzone for Windows requires Docker")
        label.setStyleSheet("QLabel { font-weight: bold; }")
        label.setAlignment(QtCore.Qt.AlignCenter)

        self.task_label = QtWidgets.QLabel()
        self.task_label.setAlignment(QtCore.Qt.AlignCenter)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setMinimum(0)

        self.install_button = QtWidgets.QPushButton("Install Docker")
        self.install_button.setStyleSheet("QPushButton { font-weight: bold; }")
        self.install_button.clicked.connect(self.install_clicked)
        self.install_button.hide()

        if platform.system() == "Darwin":
            self.launch_button = QtWidgets.QPushButton("Launch Docker")
            self.launch_button.setStyleSheet("QPushButton { font-weight: bold; }")
            self.launch_button.clicked.connect(self.launch_clicked)
            self.launch_button.hide()

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_clicked)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.install_button)
        if platform.system() == "Darwin":
            buttons_layout.addWidget(self.launch_button)
        buttons_layout.addWidget(self.cancel_button)
        buttons_layout.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(self.task_label)
        layout.addWidget(self.progress)
        layout.addLayout(buttons_layout)
        layout.addStretch()
        self.setLayout(layout)

        if platform.system == "Darwin":
            self.tmp_dir = tempfile.TemporaryDirectory(prefix="/tmp/dangerzone-docker-")
            self.installer_filename = os.path.join(self.tmp_dir.name, "Docker.dmg")
        else:
            self.tmp_dir = tempfile.TemporaryDirectory(prefix="dangerzone-docker-")
            self.installer_filename = os.path.join(
                self.tmp_dir.name, "Docker for Windows Installer.exe"
            )

        # Threads
        self.download_t = None
        self.install_t = None

    def update_progress(self, value, maximum):
        self.progress.setMaximum(maximum)
        self.progress.setValue(value)

    def update_task_label(self, s):
        self.task_label.setText(s)

    def download_finished(self):
        self.task_label.setText("Finished downloading Docker")
        self.download_t = None
        self.progress.hide()
        self.install_button.show()

    def download_failed(self, status_code):
        print(f"Download failed: status code {status_code}")
        self.download_t = None

    def download(self):
        self.task_label.setText("Downloading Docker")

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.start_download)
        self.timer.setSingleShot(True)
        self.timer.start(10)

    def start_download(self):
        self.download_t = Downloader(self.installer_filename)
        self.download_t.download_finished.connect(self.download_finished)
        self.download_t.download_failed.connect(self.download_failed)
        self.download_t.update_progress.connect(self.update_progress)
        self.download_t.start()

    def install_finished(self):
        if platform.system() == "Darwin":
            self.task_label.setText("Finished installing Docker")
            self.launch_button.show()
            self.cancel_button.setEnabled(True)
        elif platform.system == "Windows":
            self.task_label.setText("Reboot to finish installing Docker")
        self.install_t = None
        self.progress.hide()
        self.install_button.hide()

    def install_failed(self, exception):
        print(f"Install failed: {exception}")
        self.task_label.setText(f"Install failed: {exception}")
        self.install_t = None
        self.progress.hide()
        self.cancel_button.setEnabled(True)

    def install_clicked(self):
        self.task_label.setText("Installing Docker")
        self.progress.show()
        self.install_button.hide()
        self.cancel_button.setEnabled(False)

        self.progress.setMinimum(0)
        self.progress.setMaximum(0)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.start_installer)
        self.timer.setSingleShot(True)
        self.timer.start(10)

    def start_installer(self):
        self.install_t = Installer(self.common, self.installer_filename)
        self.install_t.install_finished.connect(self.install_finished)
        self.install_t.install_failed.connect(self.install_failed)
        self.install_t.update_task_label.connect(self.update_task_label)
        self.install_t.start()

    def launch_clicked(self):
        if system.platform() == "Darwin":
            print("Launching Docker")
            self.accept()
            subprocess.Popen(["open", "-a", "Docker.app"])

    def cancel_clicked(self):
        self.reject()

        if self.download_t:
            self.download_t.quit()
        if self.install_t:
            self.install_t.quit()

    def start(self):
        if not os.path.isdir("/Applications/Docker.app"):
            self.download()
        else:
            self.task_label.setText("Docker is installed, but you must launch it first")
            self.progress.hide()
            self.launch_button.show()
        return self.exec_() == QtWidgets.QDialog.Accepted


class Downloader(QtCore.QThread):
    download_finished = QtCore.pyqtSignal()
    download_failed = QtCore.pyqtSignal(int)
    update_progress = QtCore.pyqtSignal(int, int)

    def __init__(self, installer_filename):
        super(Downloader, self).__init__()
        self.installer_filename = installer_filename

        if platform.system() == "Darwin":
            self.installer_url = "https://download.docker.com/mac/stable/Docker.dmg"
        elif platform.system() == "Windows":
            self.installer_url = "https://download.docker.com/win/stable/Docker%20for%20Windows%20Installer.exe"

    def run(self):
        print(f"Downloading docker to {self.installer_filename}")
        with requests.get(self.installer_url, stream=True) as r:
            if r.status_code != 200:
                self.download_failed.emit(r.status_code)
                return
            total_bytes = int(r.headers.get("content-length"))
            downloaded_bytes = 0

            with open(self.installer_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:  # filter out keep-alive new chunks
                        downloaded_bytes += f.write(chunk)

                        self.update_progress.emit(downloaded_bytes, total_bytes)

        self.download_finished.emit()


class Installer(QtCore.QThread):
    install_finished = QtCore.pyqtSignal()
    install_failed = QtCore.pyqtSignal(str)
    update_task_label = QtCore.pyqtSignal(str)

    def __init__(self, common, installer_filename):
        super(Installer, self).__init__()
        self.common = common
        self.installer_filename = installer_filename

    def run(self):
        print(f"Installing Docker")

        if platform.system() == "Darwin":
            try:
                # Mount the dmg
                self.update_task_label.emit(f"Mounting Docker.dmg")
                subprocess.run(
                    ["hdiutil", "attach", "-nobrowse", self.installer_filename]
                )

                # Copy Docker.app to Applications
                self.update_task_label.emit("Copying Docker into Applications")
                shutil.copytree(
                    "/Volumes/Docker/Docker.app", "/Applications/Docker.app"
                )

                # Sync
                self.update_task_label.emit("Syncing filesystem")
                subprocess.run(["sync"])

                # Wait, to prevent early crash
                time.sleep(1)

                # Unmount the dmg
                self.update_task_label.emit(f"Unmounting /Volumes/Docker")
                subprocess.run(["hdiutil", "detach", "/Volumes/Docker"])

                self.install_finished.emit()

            except Exception as e:
                self.install_failed.emit(str(e))
                return

        elif platform.system() == "Windows":
            try:
                # Run the installer
                subprocess.run(
                    [self.installer_filename],
                    startupinfo=self.common.get_subprocess_startupinfo(),
                )
                self.install_finished.emit()

            except Exception as e:
                self.install_failed.emit(str(e))
                return
