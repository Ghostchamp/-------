package main

import (
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

type User struct {
	Phone string
	Name  string
	Email string
}

var users = map[string]User{}
var otpStore = map[string]string{}

func main() {
	rand.Seed(time.Now().UnixNano())
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080" // Устанавливаем порт по умолчанию
	}
	r := gin.Default()

	// Статические файлы
	r.Static("/static", "./static")

	// Роуты
	r.GET("/", homePage)
	r.POST("/auth/send-sms", sendSMS)
	r.POST("/auth/verify-sms", verifySMS)
	r.POST("/auth/register", registerUser)

	// Запуск сервера
	fmt.Println("Server is running on http://localhost:8080")
	log.Printf("Сервер запущен на порту %s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Не удалось запустить сервер: %v", err)
	}
}

func homePage(c *gin.Context) {
	c.File("./static/index.html")
}

// Отправка SMS
func sendSMS(c *gin.Context) {
	var req struct {
		Phone string `json:"phone"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	// Проверяем наличие пользователя
	if _, exists := users[req.Phone]; !exists {
		c.JSON(http.StatusNotFound, gin.H{"message": "User not found"})
		return
	}

	// Генерируем OTP
	otp := strconv.Itoa(rand.Intn(899999) + 100000)
	otpStore[req.Phone] = otp

	c.JSON(http.StatusOK, gin.H{"message": "OTP sent", "otp": otp}) // Для эмуляции возвращаем OTP
}

// Проверка SMS
func verifySMS(c *gin.Context) {
	var req struct {
		Phone string `json:"phone"`
		OTP   string `json:"otp"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	// Проверяем OTP
	if otpStore[req.Phone] != req.OTP {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid OTP"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Welcome to your dashboard"})
}

// Регистрация нового пользователя
func registerUser(c *gin.Context) {
	var req struct {
		Phone string `json:"phone"`
		Name  string `json:"name"`
		Email string `json:"email"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	// Регистрируем пользователя
	users[req.Phone] = User{
		Phone: req.Phone,
		Name:  req.Name,
		Email: req.Email,
	}

	// Генерируем OTP
	otp := strconv.Itoa(rand.Intn(899999) + 100000)
	otpStore[req.Phone] = otp

	c.JSON(http.StatusOK, gin.H{"message": "User registered, OTP sent", "otp": otp})
}
