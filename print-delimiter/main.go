package main

import (
	"fmt"
	"os"
	"strings"
	"syscall"
	"unsafe"
)

func getTerminalWidth() (int, error) {
	type winsize struct {
		Row    uint16
		Col    uint16
		Xpixel uint16
		Ypixel uint16
	}

	tty, err := os.Open("/dev/tty")
	if err != nil {
		return 0, fmt.Errorf("open /dev/tty: %w", err)
	}
	defer tty.Close()

	ws := &winsize{}
	_, _, errno := syscall.Syscall(
		syscall.SYS_IOCTL,
		tty.Fd(),
		uintptr(syscall.TIOCGWINSZ),
		uintptr(unsafe.Pointer(ws)),
	)
	if errno != 0 {
		return 0, fmt.Errorf("ioctl TIOCGWINSZ: %w", errno)
	}
	return int(ws.Col), nil
}

func main() {
	width, err := getTerminalWidth()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(strings.Repeat("-", width))
}
