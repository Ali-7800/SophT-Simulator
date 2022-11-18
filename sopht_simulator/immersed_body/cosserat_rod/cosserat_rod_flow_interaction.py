from elastica.rod.cosserat_rod import CosseratRod
import numpy as np
from sopht_simulator.immersed_body import (
    ImmersedBodyForcingGrid,
    ImmersedBodyFlowInteraction,
)


class CosseratRodFlowInteraction(ImmersedBodyFlowInteraction):
    """Class for Cosserat rod flow interaction."""

    def __init__(
        self,
        cosserat_rod: type(CosseratRod),
        eul_grid_forcing_field: np.ndarray,
        eul_grid_velocity_field: np.ndarray,
        virtual_boundary_stiffness_coeff: float,
        virtual_boundary_damping_coeff: float,
        dx: float,
        grid_dim: int,
        forcing_grid_cls: type(ImmersedBodyForcingGrid),
        real_t=np.float64,
        eul_grid_coord_shift=None,
        interp_kernel_width=None,
        enable_eul_grid_forcing_reset=False,
        num_threads=False,
        start_time=0.0,
        **forcing_grid_kwargs,
    ):
        """Class initialiser."""
        body_flow_forces = np.zeros(
            (3, cosserat_rod.n_elems + 1),
        )
        body_flow_torques = np.zeros(
            (3, cosserat_rod.n_elems),
        )
        forcing_grid = forcing_grid_cls(
            grid_dim=grid_dim,
            cosserat_rod=cosserat_rod,
            **forcing_grid_kwargs,
        )
        self.cosserat_rod = cosserat_rod
        self.cosserat_rod.element_position = np.zeros((3, cosserat_rod.n_elems))
        self.update_rod_element_position()

        # initialising super class
        super().__init__(
            eul_grid_forcing_field,
            eul_grid_velocity_field,
            body_flow_forces,
            body_flow_torques,
            forcing_grid,
            virtual_boundary_stiffness_coeff,
            virtual_boundary_damping_coeff,
            dx,
            grid_dim,
            real_t,
            eul_grid_coord_shift,
            interp_kernel_width,
            enable_eul_grid_forcing_reset,
            num_threads,
            start_time,
        )

    def update_rod_element_position(self):
        self.cosserat_rod.element_position[...] = 0.5 * (
            self.cosserat_rod.position_collection[..., 1:]
            + self.cosserat_rod.position_collection[..., :-1]
        )
