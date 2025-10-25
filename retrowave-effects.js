/**
 * Retrowave Theme JavaScript Effects
 * Дополнительные интерактивные эффекты для retrowave темы
 */

class RetrowaveEffects {
    constructor() {
        this.init();
    }

    init() {
        this.setupParticleSystem();
        this.setupGlitchEffect();
        this.setupSoundEffects();
        this.setupTypingEffect();
        this.setupScrollAnimations();
        this.setupNeonGlow();
    }

    // Система частиц для фона
    setupParticleSystem() {
        const canvas = document.createElement('canvas');
        canvas.style.position = 'fixed';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '-1';
        canvas.style.opacity = '0.3';
        document.body.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        let particles = [];

        const resizeCanvas = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };

        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);

        class Particle {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * canvas.height;
                this.vx = (Math.random() - 0.5) * 0.5;
                this.vy = (Math.random() - 0.5) * 0.5;
                this.size = Math.random() * 2 + 1;
                this.color = this.getRandomNeonColor();
                this.life = 1;
                this.decay = Math.random() * 0.02 + 0.005;
            }

            getRandomNeonColor() {
                const colors = ['#ff0080', '#00ffff', '#8000ff', '#00ff80', '#ff8000'];
                return colors[Math.floor(Math.random() * colors.length)];
            }

            update() {
                this.x += this.vx;
                this.y += this.vy;
                this.life -= this.decay;

                if (this.life <= 0) {
                    this.reset();
                }
            }

            reset() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * canvas.height;
                this.life = 1;
                this.color = this.getRandomNeonColor();
            }

            draw() {
                ctx.save();
                ctx.globalAlpha = this.life;
                ctx.fillStyle = this.color;
                ctx.shadowBlur = 10;
                ctx.shadowColor = this.color;
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }
        }

        // Создаем частицы
        for (let i = 0; i < 50; i++) {
            particles.push(new Particle());
        }

        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            particles.forEach(particle => {
                particle.update();
                particle.draw();
            });

            requestAnimationFrame(animate);
        };

        animate();
    }

    // Эффект глитча для текста
    setupGlitchEffect() {
        const glitchElements = document.querySelectorAll('[data-glitch]');
        
        glitchElements.forEach(element => {
            element.addEventListener('mouseenter', () => {
                this.triggerGlitch(element);
            });
        });
    }

    triggerGlitch(element) {
        const originalText = element.textContent;
        const glitchChars = '!@#$%^&*()_+-=[]{}|;:,.<>?';
        
        let iterations = 0;
        const maxIterations = 20;
        
        const glitchInterval = setInterval(() => {
            element.textContent = originalText
                .split('')
                .map((char, index) => {
                    if (index < iterations) return originalText[index];
                    return glitchChars[Math.floor(Math.random() * glitchChars.length)];
                })
                .join('');
            
            if (iterations >= maxIterations) {
                clearInterval(glitchInterval);
                element.textContent = originalText;
            }
            
            iterations++;
        }, 50);
    }

    // Звуковые эффекты
    setupSoundEffects() {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        // Создаем звуковые эффекты для разных элементов
        this.createSoundEffect('btn', () => this.playSynthSound(800, 1200, 0.1));
        this.createSoundEffect('card', () => this.playSynthSound(400, 600, 0.05));
        this.createSoundEffect('form-control', () => this.playSynthSound(600, 800, 0.03));
    }

    createSoundEffect(selector, soundFunction) {
        document.querySelectorAll(`.${selector}`).forEach(element => {
            element.addEventListener('mouseenter', soundFunction);
        });
    }

    playSynthSound(startFreq, endFreq, duration) {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.setValueAtTime(startFreq, audioContext.currentTime);
        oscillator.frequency.exponentialRampToValueAtTime(endFreq, audioContext.currentTime + duration);
        
        gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + duration);
    }

    // Эффект печатания
    setupTypingEffect() {
        const typingElements = document.querySelectorAll('[data-typing]');
        
        typingElements.forEach(element => {
            const text = element.textContent;
            element.textContent = '';
            element.style.borderRight = '2px solid var(--neon-cyan)';
            
            let i = 0;
            const typeWriter = () => {
                if (i < text.length) {
                    element.textContent += text.charAt(i);
                    i++;
                    setTimeout(typeWriter, 100);
                } else {
                    element.style.borderRight = 'none';
                }
            };
            
            // Запускаем с задержкой
            setTimeout(typeWriter, Math.random() * 1000);
        });
    }

    // Анимации при скролле
    setupScrollAnimations() {
        const observerOptions = {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('fade-in-up');
                    this.addNeonGlow(entry.target);
                }
            });
        }, observerOptions);

        // Наблюдаем за всеми карточками и кнопками
        document.querySelectorAll('.card, .btn, .list-group-item').forEach(element => {
            observer.observe(element);
        });
    }

    // Неоновое свечение при появлении
    addNeonGlow(element) {
        element.style.boxShadow = '0 0 20px var(--neon-cyan), 0 0 40px var(--neon-cyan)';
        
        setTimeout(() => {
            element.style.boxShadow = '';
        }, 2000);
    }

    // Дополнительные эффекты неонового свечения
    setupNeonGlow() {
        // Добавляем эффект свечения при наведении на заголовки
        document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(heading => {
            heading.addEventListener('mouseenter', () => {
                heading.style.textShadow = '0 0 20px var(--neon-cyan), 0 0 40px var(--neon-cyan), 0 0 60px var(--neon-cyan)';
            });
            
            heading.addEventListener('mouseleave', () => {
                heading.style.textShadow = '0 0 10px var(--neon-cyan)';
            });
        });
    }

    // Метод для добавления эффекта "взрыва" при клике
    addExplosionEffect(element) {
        element.addEventListener('click', (e) => {
            const rect = element.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // Создаем частицы взрыва
            for (let i = 0; i < 10; i++) {
                const particle = document.createElement('div');
                particle.style.position = 'absolute';
                particle.style.left = x + 'px';
                particle.style.top = y + 'px';
                particle.style.width = '4px';
                particle.style.height = '4px';
                particle.style.background = 'var(--neon-cyan)';
                particle.style.borderRadius = '50%';
                particle.style.pointerEvents = 'none';
                particle.style.zIndex = '1000';
                
                element.style.position = 'relative';
                element.appendChild(particle);
                
                // Анимация частицы
                const angle = (Math.PI * 2 * i) / 10;
                const velocity = 50;
                const vx = Math.cos(angle) * velocity;
                const vy = Math.sin(angle) * velocity;
                
                particle.animate([
                    { transform: 'translate(0, 0) scale(1)', opacity: 1 },
                    { transform: `translate(${vx}px, ${vy}px) scale(0)`, opacity: 0 }
                ], {
                    duration: 500,
                    easing: 'ease-out'
                }).onfinish = () => {
                    particle.remove();
                };
            }
        });
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    new RetrowaveEffects();
});

// Экспорт для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RetrowaveEffects;
}
