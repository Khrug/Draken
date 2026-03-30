from manim import *

class DrakenScene(Scene):
    def construct(self):
        # HOOK: Split screen - Wick rotation equation and monitor lizards
        divider = Line(UP * 4, DOWN * 4, color=WHITE, stroke_width=2)
        self.add(divider)
        
        # Left side: Wick rotation equation
        eq_real = MathTex(r"e^{iHt}", color=BLUE).scale(1.5).shift(LEFT * 3 + UP)
        arrow = Arrow(LEFT * 2.5, LEFT * 1.5, color=WHITE).shift(UP)
        eq_imaginary = MathTex(r"e^{-H\tau}", color=RED).scale(1.5).shift(LEFT * 1 + UP)
        
        # Right side: Two monitor lizards (represented as elongated ellipses in display posture)
        lizard1 = Ellipse(width=1.5, height=0.5, color=BLUE, fill_opacity=0.7).shift(RIGHT * 2 + UP * 0.5)
        lizard2 = Ellipse(width=1.5, height=0.5, color=BLUE, fill_opacity=0.7).shift(RIGHT * 2 + DOWN * 0.5)
        
        self.play(Write(eq_real), Create(lizard1), Create(lizard2))
        self.wait(3)
        self.play(GrowArrow(arrow))
        self.play(Transform(eq_real, eq_imaginary))
        self.wait(2)
        
        # Clear hook
        self.play(FadeOut(VGroup(eq_real, arrow, lizard1, lizard2, divider)))
        self.wait(1)
        
        # ACT 1: Build combat graph
        nodes = {}
        node_positions = {
            "Retreat": LEFT * 3 + UP * 2,
            "Approach": LEFT * 1 + UP * 2,
            "Circle": UP * 2,
            "Display": RIGHT * 1 + UP * 2,
            "Combat": RIGHT * 3 + UP * 2
        }
        
        # Create nodes one by one
        for i, (name, pos) in enumerate(node_positions.items()):
            color = GOLD if name == "Display" else BLUE
            node = Circle(radius=0.4, color=color, fill_opacity=0.8).move_to(pos)
            label = Text(name, font_size=20, color=WHITE).move_to(pos)
            nodes[name] = VGroup(node, label)
            self.play(Create(nodes[name]))
            self.wait(0.5)
        
        # Show 76% at Display with branching paths
        percent_76 = Text("76%", font_size=48, color=GOLD).next_to(nodes["Display"], DOWN)
        self.play(Write(percent_76))
        
        # Animate flow - most particles exit at Display
        for _ in range(10):
            particle = Dot(color=WHITE, radius=0.05).move_to(LEFT * 4)
            path_to_display = Line(LEFT * 4, node_positions["Display"])
            
            if np.random.random() < 0.76:  # 76% exit at display
                exit_path = Line(node_positions["Display"], node_positions["Display"] + DOWN * 2)
                self.play(MoveAlongPath(particle, path_to_display), run_time=1)
                self.play(MoveAlongPath(particle, exit_path), FadeOut(particle), run_time=0.5)
            else:  # Continue to combat
                continue_path = Line(node_positions["Display"], node_positions["Combat"])
                self.play(MoveAlongPath(particle, path_to_display), run_time=1)
                self.play(MoveAlongPath(particle, continue_path), FadeOut(particle), run_time=0.5)
        
        self.wait(2)
        
        # ACT 2: 4D vector and restriction map
        # Clear previous elements
        self.play(FadeOut(VGroup(*nodes.values(), percent_76)))
        self.wait(1)
        
        # Show 4D vector
        vector_4d = MathTex(r"x_D \in \mathbb{R}^4 = (F_{max}, E_{ratio}, \Delta m, \alpha)", 
                           color=WHITE).scale(0.8).shift(UP * 2)
        self.play(Write(vector_4d))
        
        # Visual representation of 4D vector
        vec_components = VGroup()
        for i in range(3):
            comp = Rectangle(width=0.5, height=1.5, color=BLUE, fill_opacity=0.8).shift(LEFT * 1.5 + RIGHT * i * 0.7)
            vec_components.add(comp)
        
        # Alpha dimension - translucent red
        alpha_comp = Rectangle(width=0.5, height=1.5, color=RED, fill_opacity=0.4).shift(LEFT * 1.5 + RIGHT * 3 * 0.7)
        alpha_label = Text("α", color=RED, font_size=24).next_to(alpha_comp, DOWN)
        
        vec_components.add(alpha_comp)
        self.play(Create(vec_components), Write(alpha_label))
        self.wait(2)
        
        # Restriction map
        restriction_eq = MathTex(r"\rho_{D \to Cl} = [I_3 | 0] : \mathbb{R}^4 \to \mathbb{R}^3", 
                                color=WHITE).scale(0.8)
        self.play(Write(restriction_eq))
        
        # Show alpha dimension dissolving
        self.play(FadeOut(alpha_comp), FadeOut(alpha_label))
        self.wait(1)
        
        # Parallel Wick rotation equation
        wick_parallel = MathTex(r"e^{iHt} \to e^{-H\tau}", color=RED).scale(0.8).shift(DOWN * 1.5)
        self.play(Write(wick_parallel))
        self.wait(3)
        
        # ACT 3: Zoom out through layers
        self.play(FadeOut(VGroup(vector_4d, vec_components, restriction_eq, wick_parallel)))
        self.wait(1)
        
        # Show multiple layers with imaginary dimensions
        layers = [
            ("Varanid Combat", "L05-L06"),
            ("Financial Derivatives", "L11"),
            ("Immune Anticipation", "L03"),
            ("Predictive Coding", "L07")
        ]
        
        layer_group = VGroup()
        for i, (name, level) in enumerate(layers):
            layer_rect = Rectangle(width=6, height=0.8, color=BLUE, fill_opacity=0.3)
            layer_rect.shift(UP * (2 - i * 0.9))
            
            layer_text = Text(name, font_size=20).move_to(layer_rect.get_left() + RIGHT * 0.5)
            level_text = Text(level, font_size=16, color=GOLD).move_to(layer_rect.get_right() + LEFT * 0.5)
            
            # Imaginary dimension thread
            alpha_thread = Line(layer_rect.get_center() + LEFT * 2, 
                               layer_rect.get_center() + LEFT * 1.5, 
                               color=RED, stroke_width=3)
            
            layer_assembly = VGroup(layer_rect, layer_text, level_text, alpha_thread)
            layer_group.add(layer_assembly)
            
            self.play(Create(layer_assembly))
            self.wait(0.5)
        
        # Red-to-blue collapse pattern
        for layer in layer_group:
            alpha_thread = layer[-1]  # Last element is the alpha thread
            self.play(alpha_thread.animate.set_color(BLUE), run_time=0.3)
            self.play(alpha_thread.animate.set_color(RED), run_time=0.3)
        
        self.wait(2)
        
        # CONCLUSION: Final pullback
        # Shrink to point in manifold
        self.play(layer_group.animate.scale(0.1).move_to(ORIGIN))
        
        # Show full 18-layer manifold architecture
        manifold_outline = Rectangle(width=8, height=6, color=GOLD, stroke_width=3)
        self.play(Create(manifold_outline))
        
        # Final optimization axiom with glowing imaginary dimension
        final_eq = MathTex(r"\Diamond \min S_{sys}(t) \text{ s.t. } \frac{dH}{dt} \geq 0 \Diamond", 
                          color=WHITE).scale(1.2)
        imaginary_glow = Circle(radius=2, color=RED, fill_opacity=0.1, stroke_opacity=0.3)
        
        self.play(Write(final_eq))
        self.play(Create(imaginary_glow))
        self.play(imaginary_glow.animate.set_fill_opacity(0.3), run_time=2)
        
        self.wait(3)