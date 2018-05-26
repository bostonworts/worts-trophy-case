Rails.application.routes.draw do
  root "trophies#index"

  resources :trophies, only: [:index, :new]
end
